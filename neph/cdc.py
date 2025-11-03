from fastapi import FastAPI, Request
import uvicorn
from uvicorn.config import LOGGING_CONFIG
import json
from multiprocessing import Process
from neo4j import Session
from typing import Tuple
import time

from .settings import Settings
from .db import add_session, CypherQuery, PartialCypherQuery
from .nodes import record_to_stub
from .exceptions import LoggedException
from .workflow import analyze_node_or_stub
from .log import logger, log_fmt
from .plugins import load_all_plugins


app = FastAPI()

"""
This is not the real CDC mechanism as that requires Neo4j Enterprise
This uses the APOC trigger mechanism to call a query on events like node creations. 
The intended use is to subscribe to node creation events then
post the node data to a web hook. This then triggers an analysis
workflow to enrich the nodes and build relationships.
Currently, the relationship building must use SQL to populate data for many-to-many (Assoc)
relationships as the CDC in unaware of the original ingestion mechanism (e.g. if JSONL was used).

___
Notes:
To install the trigger (in system db)
call apoc.trigger.install('<db>', '<trigger name>', 'unwind $createdNodes as node call apoc.load.jsonParams("<webhook url>", {method:"POST"}, apoc.convert.toJson(node) ) yield value return value', {phase: "afterAsync"})

APOC links
- Triggers overview: https://neo4j.com/docs/apoc/current/background-operations/triggers/
- Install trigger: https://neo4j.com/docs/apoc/current/overview/apoc.trigger/apoc.trigger.install/
- POST JSON: https://neo4j.com/docs/apoc/current/overview/apoc.load/apoc.load.jsonParams/
- Convert node->JSON: https://neo4j.com/docs/apoc/5/overview/apoc.convert/apoc.convert.toJson/
"""


# cannot have a param of dict/json type as it requires
# the request set a content type header
#   trying to do this in Cypher via APOC jsonParams doesnt seem to work
#   when setting the header in the config map
#   so just bypassing it
#
# Ex:
#   call apoc.load.jsonParams("<url>", {method: "POST"}, apoc.convert.toJson(n)) yield value
#   works but
#   call apoc.load.jsonParams("<url>", {method: "POST", Content-Type: "application/json"}, ...
#   doesnt, nor does ... "Content-Type": "application/json" ...

# Fastapi (or another app server) seems like a lot here but
# using the built-in SimpleHTTPServer requires a lot of handling
# for just accessing and working with the data.
# e.g. just reading the POST body was not obvious since the APOC
# HTTP requests didn't have content-length headers
# Also, at some point in the future, I'd like to expose a REST
# API, so I can tie that into this app instance


@app.post(Settings.cdc_uri, status_code=201)
async def recv_cdc_data(request: Request):
    """
    Web hook method for receiving trigger data.
    Request body format is a standard node record as you would receive from a call to session.run(...).
    """

    data = await request.body()
    data = json.loads(data)
    logger.debug(f'Received trigger data: "{json.dumps(data)}"')
    stub = record_to_stub(data)
    analyze_node_or_stub(stub)


def generate_cdc_install_query() -> Tuple[CypherQuery, PartialCypherQuery]:
    """
    Generate a trigger installation Cypher query, which is compromised of two separate queries.
    The outer query installs the trigger. The inner query is a query that gets called when the trigger occurs.
    This returns both the inner query and the final, joined query
    """

    # calling install with a dupe name should overwrite the existing trigger of the same name
    cdc_url = f"{Settings.cdc_url}?id="
    inner_query = f"""unwind $createdNodes as node call apoc.load.jsonParams("{cdc_url}" + elementId(node), {{method:"POST"}}, apoc.convert.toJson(node) ) yield value return value"""
    final_query = f"""call apoc.trigger.install('{Settings.neo4j_db}', '{Settings.cdc_trigger}', '{inner_query}', {{phase: "afterAsync"}})"""
    return final_query, inner_query


@add_session()
def verify_trigger(wait_time: int = 120, session: Session = None) -> bool:
    """
    APOC triggers are eventually consistent, so they may not appear immediately after installation.
    This polls the database periodically until the trigger appears in the trigger list, based on the
    trigger name and inner query.
    Keep in mind that the trigger name is based on Settings.cdc_trigger. If you change this value
    between uses, it may lead to duplicate trigger installations and/or failing this verification check.
    """

    # querying triggers occurs in the database whereas installation occurs in the system db
    _, query = generate_cdc_install_query()

    # trigger installation is eventually consistently, so you
    # need to keep checking until its installed
    # same for deleting triggers
    start_time = time.time()
    loop_sleep = int(wait_time / 10)
    while True:
        current_time = time.time()
        if current_time - start_time >= wait_time:
            break

        triggers = session.run("""call apoc.trigger.list()""").values()
        if len(triggers) > 0:
            for trigger in triggers:
                trigger_name = trigger[0]
                trigger_query = trigger[1]
                # check for a trigger with the name and query matching the one that gets installed
                if trigger_name == Settings.cdc_trigger and trigger_query == query:
                    return True
                else:
                    time.sleep(loop_sleep)

    return False


@add_session(database="system")
def install_trigger(session: Session = None, verify: bool = True):
    """
    Install the CDC trigger in the System database
    """

    query, _ = generate_cdc_install_query()
    session.run(query)

    if verify:
        # currently assuming a refresh interval of 1 minute
        # (1m/60000ms = default used by APOC)
        # so we will wait 2 cycles, checking once every 12 seconds
        verified = verify_trigger(wait_time=120)
        if not verified:
            raise LoggedException("Trigger not verified")


def fixup_logging_config(config: dict):
    """
    Override the uvicorn logging config used by FastAPI to use the same format and log file as Neph
    """

    # expected to work against the default
    # logger config of uvicorn.config.LOGGING_CONFIG
    # see also: https://github.com/fastapi/fastapi/issues/1508

    # change log format to use same as main logger
    config["formatters"]["access"]["fmt"] = log_fmt
    config["formatters"]["default"]["fmt"] = log_fmt

    # configure logging to a separate log file
    config["handlers"]["default"]["class"] = "logging.FileHandler"
    config["handlers"]["default"]["filename"] = Settings.cdc_log_file
    del config["handlers"]["default"]["stream"]
    config["handlers"]["access"]["class"] = "logging.FileHandler"
    config["handlers"]["access"]["filename"] = Settings.cdc_log_file
    del config["handlers"]["access"]["stream"]


def start_cdc_server(override_logging: bool = True, install: bool = True) -> Process:
    """
    Start a CDC API server in the background. Optionally install the APOC trigger and update the API server logging
    config.
    """

    # lot of discussion around how best to handle uvicorn programmatically
    #   like: https://github.com/encode/uvicorn/issues/742 & https://github.com/encode/uvicorn/discussions/1103
    # but this seems like the cleanest

    # CDC likely to be run out-of-band to normal Neph usage so loading plugins here to be safe
    load_all_plugins()

    if install:
        install_trigger()

    log_config = LOGGING_CONFIG
    if override_logging:
        fixup_logging_config(log_config)
    config = uvicorn.Config(app, host=Settings.cdc_host, port=Settings.cdc_port, log_config=log_config)
    server = uvicorn.Server(config)

    # TODO: context handler for this -> process.terminate() ?
    process = Process(target=server.run, daemon=True)
    process.start()
    return process
