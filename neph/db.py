from contextlib import contextmanager
from neo4j import GraphDatabase, Session
from typing import Tuple
from functools import wraps

from .settings import Settings
from .log import logger


type CypherQuery = str
"""Cypher query as a string"""
type PartialCypherQuery = str
"""Partial Cypher query as a string. Cannot be run on its own."""
type QueryParameters = dict
"""Dict of query parameters to pass to session.run. May be empty"""
type QueryWithParameters = Tuple[CypherQuery, QueryParameters]
"""Cypher query string and parameters"""


@contextmanager
def session(database: str = None):
    """
    Neo4j client session context manager
    """
    if not database:
        database = Settings.neo4j_db

    with GraphDatabase.driver(Settings.neo4j_url, auth=(Settings.neo4j_user, Settings.neo4j_password)) as driver:
        # driver.verify_connectivity()

        # note: when running queries using a session, need to consume the results within the context manager,
        #       otherwise you will trigger a ResultConsumedError since they expire with the session
        with driver.session(database=database) as session_:
            original_session_run = session_.run

            # override the run method to log the cypher query
            # will be logged at debug level, so requires
            # configuring the "log_level" setting to "debug"
            def logged_run(*args, **kwargs):
                # check if passed explicitly as kwarg
                if "query" in kwargs:
                    query: str = kwargs.get("query")
                # otherwise it will be the first positional arg
                else:
                    query: str = args[0]
                query = query.replace("\n", "\\n")
                logger.debug(f"Issuing Cypher query: {query}")
                return original_session_run(*args, **kwargs)

            session_.run = logged_run
            yield session_


def add_session(database: str = None):
    """
    Decorator function for adding a Neo4j Session into the function.
    Requires updating the function signature to include a "session" variable.

    Example:
        def foo(bar: str)
        becomes
        def foo(bar: str, session: Session = None)
    """

    def outer(f):
        @wraps(f)
        def inner(*args, **kwargs):
            with session(database=database) as s:
                if "session" not in kwargs:  # allow overriding session
                    kwargs["session"] = s
                return f(*args, **kwargs)

        return inner

    return outer


def verify_neo4j_connection():
    with GraphDatabase.driver(Settings.neo4j_url, auth=(Settings.neo4j_user, Settings.neo4j_password)) as driver:
        driver.verify_connectivity()


@add_session()
def connections_not_ready(session: Session = None):
    """
    Query the number of Steampipe connections that are not yet ready.

    For example, if you have an AWS config file with many accounts, Steampipe
    will load the connections asynchronously. When you attempt to query an aggregator
    containing those connections, they will be silently skipped. You should
    first await all connections before querying.
    """

    # https://github.com/turbot/steampipe/blob/develop/design/connection_status_table.md
    query = f"""CALL apoc.load.jdbc($jdbc_url, $query) yield row 
    return row"""
    results = session.run(
        query,
        parameters={
            "jdbc_url": Settings.steampipe_jdbc_url,
            "query": "select count(name) as ct from steampipe_connection where state <> 'ready'",
        },
    ).values()[0][0]
    count = results.get("ct", 0)
    return count


def sql_in_cypher(sql_query: str, cypher_query: str, batch: bool = True) -> QueryWithParameters:
    """
    Generate a Cypher query for performing a SQL query against the Steampipe database
    then using the results with an inner Cypher query. The inner Cypher query
    should expect the row data to be returned, unwound as "r".
    If batching is required, the outer Cypher query will use apoc.periodic.iterate
    with the project-configured batch size (Settings.jdbc_batch_size).

    Example: Query a SQL table then create a node for each row
        input:
            SQL: SELECT * FROM table
            Cypher: MERGE (n:label{id: r.id}) SET n = r
        output (not-batched):
            CALL apoc.load.jdbc("<jdbc_url>", "SELECT * FROM table") yield row
            UNWIND row as r
            MERGE (n:label{id: r.id}) SET n = r
        output (batched):
            CALL apoc.periodic.iterate(
              "CALL apoc.load.jdbc('<jdbc_url>', 'SELECT * FROM table')",
              'UNWIND row as r MERGE (n:label{id: r.id}) SET n = r',
              {{ batchSize: $batch_size, parallel:false }}
            )

    This function will return the final query and a dict of parameters to be passed
    into the session as query parameters.
    """

    if not batch:
        cypher = f"""
        CALL apoc.load.jdbc("{Settings.steampipe_jdbc_url}", "{sql_query}") yield row 
        UNWIND row as r
        {cypher_query}
        """
        parameters = dict()
    else:
        cypher = f"""
        CALL apoc.periodic.iterate(
          "CALL apoc.load.jdbc('{Settings.steampipe_jdbc_url}', '{sql_query}')",
          'UNWIND row as r {cypher_query}',
          {{ batchSize: $batch_size, parallel:false }}
        )
        """
        # originally, the jdbc url and table query were parameters,
        # but since theyre nested in the inner call, it doesnt work
        # w/o cypher string concatenation (e.g. 'CALL ... '+$jdbc_url+ '...')
        #   (afaik, there is no string interpolation in cypher)
        # may revisit in the future though
        parameters = {"batch_size": Settings.jdbc_batch_size}

    return cypher, parameters
