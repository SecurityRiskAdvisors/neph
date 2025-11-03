from neo4j import Session
from typing import TypeVar, List, Optional, Tuple, Type
from enum import Enum, auto
from abc import abstractmethod, ABC
import json

from .utils import get_subclasses, cast_table_query
from .db import add_session, sql_in_cypher, CypherQuery, QueryWithParameters
from .settings import Settings
from .nodes import BaseGraphNodeT
from .exceptions import EdgeTableNotFound
from .log import logger


# TODO: better way to add conditions to cypher queries?
#       either neomodel or https://github.com/Mizzlr/pycypher


# TODO: should cast relation properties to strings via some method
#       rather than expect it by convention


def jsonlist_query_unroll_end(
    start_label: str,
    end_label: str,
    start_property: str,
    end_property: str,
    relation: str,
    nested_end_property: str = None,
    invert_rel_direction: bool = False,
) -> CypherQuery:
    """
    Generate a query to map two node types together based on the end node's property.
    Property is expected to be a serialized JSON list.

    Example:
        end: Group { users: '[user1, user2, user3]' }
        start: User { name }
    will match the User's name property to the user in the users list after deserializing

    If the JSON list if a list of other objects rather than strings,
    you can use the nested_end_property to specify the nested object
    property name for the final property comparison

    Example:
        end: Group { users: '[{UserName: user1, ... }]' }
        start: User { name }
        nested_end_property = UserName (to compare User.name to each UserName)
    """
    nested_end_property = f".{nested_end_property}" if nested_end_property else ""

    start_rel_segment = "-" if not invert_rel_direction else "<-"
    end_rel_segment = "->" if not invert_rel_direction else "-"

    # either standard: (start)  -[:RELATION]-> (end)
    # or inverted    : (start) <-[:RELATION]-  (end)
    relation_path = f"(start){start_rel_segment}[:{relation}]{end_rel_segment}(end)"

    return f"""
    MATCH (end:{end_label})
    WITH *, apoc.convert.fromJsonList(end.{end_property}) as {end_property}_list
    UNWIND {end_property}_list as {end_property}_item
    MATCH (start:{start_label})
    WHERE start.{start_property} = {end_property}_item{nested_end_property}
    MERGE {relation_path}
    """


class BaseRelationship(ABC):
    """
    Base relationship class
    """

    start: BaseGraphNodeT
    end: BaseGraphNodeT
    # https://neo4j.com/docs/cypher-manual/current/syntax/naming/
    # node labels:    pascal-cased + no spaces/underscores    FooBar
    # relationships:  upper-cased  + underscored              FOO_BAR
    relation: str
    start_property: str
    end_property: str

    relation_properties: Optional[List[str]] = list()

    @classmethod
    @abstractmethod
    def populate(cls):
        pass


class BasicRelationship(BaseRelationship):
    """
    Base basic relationship class.
    Node matching is based on the start label + start property matching the end label + end property.
    """

    # adds start.account_id = end.account_id to where condition
    #
    # note: TBH im not sure if ID collisions are possible, but I would assume they are not
    #       not much harm in having it anyways
    #
    #       https://repost.aws/questions/QUo8PH97hlS0KwUx5tNIc4JQ/instance-id-uniqueness
    #       -> globally unique forever for EC2
    #       but other resource IDs may vary
    account_match: bool = False

    @classmethod
    def query(cls) -> CypherQuery:
        account_condition = f"""and start.account_id = end.account_id""" if cls.account_match else ""
        return f"""
        MATCH (start:{cls.start.label})
        MATCH (end:{cls.end.label})
        WHERE start.{cls.start_property} = end.{cls.end_property} {account_condition}
        MERGE (start)-[:{cls.relation}]->(end)
        """

    @classmethod
    @add_session()
    def populate(cls, session: Session = None):
        """
        Main function used to create the relationship
        """
        session.run(cls.query())


class AssocDataType(Enum):
    Sql = auto()
    Jsonl = auto()


class AssocRelationship(BaseRelationship):
    """
    Base association relationship class.
    This relationship type is meant for instances where two nodes are related via a third table.
    For example, a user table being related to a group table via a many-to-many user-group membership table.
    Node matching is based on the start label + start property matching the association node start property
    and the end label + end property matching that same node's end property.
    E.g. Start1.PropertyA = Association1.PropertyB and Association1.PropertyC = End1.PropertyD.
    Unlike other relationship types, this relationship also expects a table.
    """

    start_rel_property: str
    end_rel_property: str
    table: str

    @classmethod
    def _data_query_sql(cls) -> QueryWithParameters:
        # cypher query will be appended in main query body
        return sql_in_cypher(sql_query=cast_table_query(cls.table), cypher_query="", batch=False)

    @classmethod
    def _data_query_jsonl(cls, data: List[dict]) -> QueryWithParameters:
        # TODO: max parameter size?
        new_rows = []
        # pull out just the properties required by the relationship
        for row in data:
            new_row = dict()
            new_row[cls.start_rel_property] = row.get(cls.start_rel_property, "")
            new_row[cls.end_rel_property] = row.get(cls.end_rel_property, "")
            if cls.relation_properties and len(cls.relation_properties) > 0:
                for prop in cls.relation_properties:
                    new_row[prop] = row.get(prop, "")
            new_rows.append(new_row)

        query = "UNWIND $rows as r"
        parameters = {"rows": new_rows}
        return query, parameters

    @classmethod
    def query(cls, data_type: AssocDataType = AssocDataType.Sql, **data_kwargs) -> QueryWithParameters:

        # format relationship properties as a string
        # expects the conventional "r" as the row identifier
        if not cls.relation_properties:
            relation = f":{cls.relation}"
        else:
            properties_str = ",".join([f"{prop}: r.{prop}" for prop in cls.relation_properties])
            properties_str = f"{{ {properties_str} }}"
            relation = f":{cls.relation}{properties_str}"

        # TODO: need a way to select this dynamically
        if data_type == AssocDataType.Sql:
            query, parameters = cls._data_query_sql()
        else:
            query, parameters = cls._data_query_jsonl(**data_kwargs)

        query += f"""
        MATCH (start:{cls.start.label})
        MATCH (end:{cls.end.label})
        WHERE start.{cls.start_property} = r.{cls.start_rel_property} and end.{cls.end_property} = r.{cls.end_rel_property}
        MERGE (start)-[{relation}]->(end)
        """

        return query, parameters

    @classmethod
    @add_session()
    def populate(cls, session: Session = None, **query_kwargs):
        """
        Main function used to create the relationship
        """
        query, parameters = cls.query(**query_kwargs)
        session.run(query, parameters=parameters)


BaseRelationshipT = TypeVar("BaseRelationshipT", bound=Type[BaseRelationship])


def edges() -> List[BaseRelationshipT]:
    """
    Get all child relationship classes of the base relationship class while
    excluding sub-parent classes.
    Will filter out association relationships that use tables designated as
    AWS Organization tables if Organization loading is disabled.
    """

    subclasses = get_subclasses(BaseRelationship)
    subclasses.discard(AssocRelationship)
    subclasses.discard(BasicRelationship)

    # remove assoc relationships from list if the rel uses an org table
    if not Settings.load_aws_org:
        filt_subclasses = []
        for subclass in subclasses:
            if issubclass(subclass, AssocRelationship):
                if subclass.table not in Settings.aws_org_tables:
                    filt_subclasses.append(subclass)
            else:
                filt_subclasses.append(subclass)
        subclasses = filt_subclasses

    return list(subclasses)


def get_edges_by_table_name(table_name) -> List[BaseRelationshipT]:
    """
    Get all association relationships that use a table of the given name
    """

    all_edge_cls = [edge_cls for edge_cls in get_subclasses(AssocRelationship) if edge_cls.table == table_name]
    if len(all_edge_cls) == 0:
        raise EdgeTableNotFound(f'Cannot find relationship with table "{table_name}"')

    return all_edge_cls


def populate_base_relationships(node_types: List[BaseGraphNodeT] = None, exclude_assoc: bool = False):
    """
    Populate all relationships that involve on or more of the provided node types
    """

    node_types = node_types if node_types else []

    # get all subclasses of baserelationship then run the populate method on each
    for edge in edges():
        if len(node_types) > 0 and (edge.start in node_types or edge.end in node_types):

            if exclude_assoc and issubclass(edge, AssocRelationship):
                continue

            try:
                edge.populate()
            except Exception as e:
                logger.warn(f'Error for edge "{edge.__name__}" ({e})')
