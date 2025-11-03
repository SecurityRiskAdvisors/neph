import fnmatch
import re
from abc import abstractmethod
from typing import TypeVar, Optional, List, Type, Self
from neo4j.graph import Node
from neo4j import Session
from dataclasses import dataclass, field, make_dataclass
from abc import ABC

from .exceptions import NodeTableNotFound, NodeNotFound
from .db import add_session, sql_in_cypher, PartialCypherQuery
from .settings import Settings
from .utils import ARN, cast_table_query, get_subclasses, match_subclass
from .log import logger


type RecordDict = dict
"""Graph data in JSON as returned from a query to the database"""


class GraphNodeStub:
    """
    Parent class for generated stub class types.
    """

    def __init__(self):
        super().__init__()
        self._neph_parent_node = None

    def get_parent(self) -> "BaseGraphNodeT":
        """
        Parent graph node class for the stub
        """

        return self._neph_parent_node

    def set_parent(self, value):
        self._neph_parent_node = value

    def __str__(self):
        return f"({self._neph_parent_node.label}{{{self._neph_parent_node.id}:'{getattr(self, self._neph_parent_node.id)}'}})"


GraphNodeStubT = TypeVar("GraphNodeStubT", bound=GraphNodeStub)


@dataclass
class BaseGraphNode(ABC):
    """
    Base node class

    This class is used for representing graph nodes types but does not contain
    the node properties. Node stubs are in-Python representations of the graph nodes
    with the node properties present.

    To add a new resource type to the graph, simply subclass this class. It will then
    be included in ingestion functions. This can be done via a plugin (see plugins.py).
    """

    table: str
    id: str
    # use the label for queries
    # use cls.__name__ for everything else (e.g. class matching)
    label: str
    # some tables requiring filtering on a type, such as Organization policies
    # without a where = '...' filter on the query, you cannot retrieve rows
    # (in the table source code, look for KeyColumns within the ListConfig)
    types: Optional[List[str]] = field(default_factory=list)

    # override the SQL select query for upsertion
    # mutually exclusive with types property
    table_query: Optional[str] = None

    @classmethod
    def stub(cls, data: dict) -> GraphNodeStubT:
        """
        Generate a stub class for the node type then instantiate an instance of it.

        Stubs are the in-code representation of the graph node, both of which are
        based on the table columns.
        Stub object are dataclasses and all properties are either strings or None
        (same as the graph, where all properties are cast as varchars)
        Stubs are useful for when you want to work against the results of a query
        within your code. E.g. you can pass the a result from session.run(query)
        into record_to_stub(...) to get a dataclasse of that result then perform
        actions against the properties using dot accessors
        """

        columns = Settings.steampipe_tables_schema.get(cls.table, [])
        fields = [(column, str | None, field(default=None)) for column in columns]
        stub_cls = make_dataclass(f"{cls.label}Stub", fields, bases=(GraphNodeStub,))
        # ignore properties outside the schema (e.g. enrichments)
        data = {k: v for k, v in data.items() if k in columns}
        stub_inst = stub_cls(**data)
        stub_inst.set_parent(cls)
        return stub_inst

    @classmethod
    @add_session()
    def upsert_bulk_from_sql(cls, session: Session = None):
        """
        Nodes upsertion logic for SQL
        """
        # TODO: would be nice to use an AST instead of concatenating strings. or an ORM-like mechanism
        if cls.table_query:
            table_query = cls.table_query
        else:
            table_query = cast_table_query(cls.table)
            if hasattr(cls, "types"):
                if len(cls.types) > 0:
                    type_str = ", ".join(f"'{type_}'" for type_ in cls.types)
                    table_query += f" where type in ({type_str})"

        inner_cypher = f"""MERGE (n:{cls.label}{{{cls.id}: r.{cls.id}, account_id: r.account_id}}) SET n = r"""
        query, parameters = sql_in_cypher(sql_query=table_query, cypher_query=inner_cypher, batch=True)

        session.run(query, parameters=parameters)

    @classmethod
    @add_session()
    def upsert_bulk_from_jsonl(cls, properties_list: List[dict], session: Session = None):
        """
        Nodes upsertion logic for JSONL
        """
        # this generates single a query that upserts every row
        # in the list by providing the row as a query parameter

        # force cast all properties to strings to mirror sql casting
        # and exclude empty values
        # also need to verify ID property is present
        bulk_params = []
        for properties in properties_list:  # type: dict
            if cls.id not in properties:
                err = f'Node properties do not include required ID property "{cls.id}" for node "{cls.__name__}" '
                # raise NodePropertyError(err)
                logger.warn(err)

            cast_properties = {k: str(v) for k, v in properties.items() if v is not None}
            bulk_params.append(cast_properties)

        bulk_query = f"""
        UNWIND $nodes as node
        MERGE (n:{cls.label}{{ {cls.id}: node.{cls.id}, account_id: node.account_id }})
        SET n=node
        """
        session.run(bulk_query, parameters={"nodes": bulk_params})

    # ideally, the input list would be a list of properties
    #   like: [ Node.name, Node.arn, ... ]
    # but this would likely require something convoluted to achieve
    @classmethod
    def as_match(cls, properties: dict, merge: bool = True, node_name: str = "node") -> PartialCypherQuery:
        """
        Generate a Cypher MATCH/MERGE statement for the node class using the given properties
        """
        # properties is a dict of property names to property values to match on
        properties_str = ",".join([f'{k}: "{v}"' for k, v in properties.items()])
        properties_str = f"{{ {properties_str} }}"
        operation = "MERGE" if merge else "MATCH"
        return f"""{operation} ({node_name}:{cls.label}{properties_str})"""


BaseGraphNodeT = TypeVar("BaseGraphNodeT", bound=Type[BaseGraphNode])


class FakeGraphNode(BaseGraphNode):
    """
    Fake nodes are nodes that appear in the graph but that are not based on a
    Steampipe table. The should work similar to real nodes but operations
    dealing with their tables and upsertion are essentially no-ops.
    An example of a fake node would be the "Service" fixture nodes. These represent
    AWS Services themselves.
    """

    @classmethod
    @abstractmethod
    def columns(cls) -> List[str]:
        pass

    @classmethod
    def stub(cls, data: dict) -> GraphNodeStubT:
        fields = [(column, str | None, field(default=None)) for column in cls.columns()]
        stub_cls = make_dataclass(f"{cls.label}Stub", fields, bases=(GraphNodeStub,))
        # ignore properties outside the schema (e.g. enrichments)
        data = {k: v for k, v in data.items() if k in cls.columns()}
        stub_inst = stub_cls(**data)
        stub_inst.set_parent(cls)
        return stub_inst

    @classmethod
    def upsert_bulk_from_sql(cls, *args, **kwargs):
        pass

    @classmethod
    def upsert_bulk_from_jsonl(cls, *args, **kwargs):
        pass


@dataclass
class NodeFinder:
    """
    Utility class for generating Cypher queries to match nodes using a search criteria.
    """

    label: str
    id_value: str

    @classmethod
    def from_str(cls, v: str) -> Self:
        """
        Derive from a finder string of the format:
            <node label> | <node id value>
        For example:
            IamUser|arn:aws:iam::123456789012:user/user1
        """
        parts = v.split("|")
        label = parts[0]
        id_value = "".join(parts[1:])
        return cls(label=label.strip(), id_value=id_value.strip())

    @property
    def node(self) -> BaseGraphNodeT:
        return match_subclass(BaseGraphNode, self.label)

    def cypher(self, **kwargs) -> PartialCypherQuery:
        return self.node.as_match(properties={self.node.id: self.id_value}, merge=False, **kwargs)


def nodes(include_fakes: bool = False) -> List[BaseGraphNodeT]:
    """
    Get all child relationship classes of the base node class.
    Will filter nodes that use tables designated as AWS Organization tables
    if Organization loading is disabled.
    """

    subclasses = get_subclasses(BaseGraphNode)
    subclasses.discard(FakeGraphNode)
    if not include_fakes:
        fake_subclasses = get_subclasses(FakeGraphNode)
        subclasses.difference_update(fake_subclasses)

    # remove nodes from list if the node uses an org table
    if not Settings.load_aws_org:
        subclasses = [subclass for subclass in subclasses if subclass.table not in Settings.aws_org_tables]

    return subclasses


def get_node_by_property(property, value, **node_kwargs) -> BaseGraphNodeT:
    """
    Get a node class based on its class property
    """
    try:
        node_cls = next(filter(lambda x: getattr(x, property) == value, nodes(**node_kwargs)))
    except StopIteration:
        raise NodeNotFound(f'Cannot find node where "{property}" is "{value}"')
    else:
        return node_cls


def get_node_by_table_name(table_name, **kwargs) -> BaseGraphNodeT:
    """
    Get a node class based on its table
    """
    return get_node_by_property("table", table_name, **kwargs)


def get_node_by_label(label, **kwargs) -> BaseGraphNodeT:
    """
    Get a node class based on its label
    """
    return get_node_by_property("label", label, **kwargs)


# TODO: fixup the how/when fakes are included not included
def record_to_stub(record: RecordDict | Node, include_fakes: bool = False) -> GraphNodeStubT:
    """
    Convert a query record (returned from session.run(...)) into a stub
    by resolving the label in the record to its corresponding node class.
    """

    if isinstance(record, dict):
        labels = record.get("labels")
        properties = record.get("properties")
    else:
        labels = list(record.labels)
        properties = record
    label = labels[0]
    node_cls = get_node_by_label(label, include_fakes=include_fakes)
    stub = node_cls.stub(data=properties)
    return stub


@add_session()
def get_stub_by_id(table_name: str, id_value, session: Session = None) -> GraphNodeStubT:
    """
    Resolve the table to its corresponding node class then find the first node of that
    type in the database where its ID property matches the provided ID value.
    """

    try:
        node_cls: BaseGraphNodeT = get_node_by_table_name(table_name)
    except KeyError:
        raise NodeTableNotFound(f'Node table "{table_name}" not found')

    query = f"""MATCH (n:{node_cls.label} {{{node_cls.id}:"{id_value}"}}) return n as node limit 1"""

    records = session.run(query).values()

    if len(records) > 0:
        stub = node_cls.stub(data=records[0][0])
        return stub
    else:
        raise NodeNotFound(f'Node with ID "{id_value}" ("{table_name}") not found')


@add_session()
def get_stub_by_arn(arn: str | ARN, session: Session = None) -> GraphNodeStubT:
    """
    Find the first node in the database with an ARN that matches the provided value.
    For ephemeral ARN types, resolves them to their in-database equivalent
    (e.g. Assumed roles -> Role)
    """

    if isinstance(arn, str):
        arn = ARN.from_string(arn)

    # assumed roles are not long-term resources, they are projected from roles
    # so they nede to be converted to role arns in order to resolve them to graph nodes
    # example:
    #   role: arn:aws:iam::1234:role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig
    #   will have an assumed role arn of arn:aws:sts::1234:assumed-role/AWSServiceRoleForConfig/abcd
    #   so if you try to convert back from assumed role -> role, the ARNs will not match
    if arn.resource_type == "role":
        role_name = arn.resource_id.split("/")[-1]  # node names do not include the path
        query = f"""MATCH (n:IamRole{{name:"{role_name}", account_id:"{arn.account_id}"}}) return n as node limit 1"""
    else:
        query = f"""MATCH (n{{arn:"{arn}"}}) return n as node limit 1"""

    records = session.run(query).values()

    if len(records) > 0:
        node = record_to_stub(records[0][0])  # just assumes theres exactly 1 result
        return node
    else:
        raise NodeNotFound(f'Node with ARN "{arn}" not found')


@add_session()
def upsert_resource_node_from_arn(resource: ARN | str, session: Session = None):
    """
    Update or create a node based on the provided ARN.
    When creating a node, it will have a single property of the ARN.
    """

    if isinstance(resource, str):
        resource = ARN.from_string(resource)

    # check if the provided arn matches any arn patterns for the service
    service_resources = Settings.iam_data.resources.get_resource_types_for_service(resource.service)
    arn_matches = []
    for service_resource in service_resources:
        resource_details = Settings.iam_data.resources.get_resource_type_details(resource.service, service_resource)
        if arn_pattern := resource_details.get("arn", None):
            arn_fn_pattern = re.sub(r"\${.*?}", "*", arn_pattern)
            arn_match = fnmatch.fnmatch(str(resource), arn_fn_pattern)
            arn_matches.append(arn_match)
    positive_match = any(arn_matches)

    # if Settings.iam_data.resources.resource_type_exists(resource.service, resource.resource_type):
    # ^^ this doesnt work since some ARNs dont have a resource type (e.g. S3 buckets just have the bucket name)
    #    so you need to match based on the ARN pattern match
    if positive_match:
        # resource_details = Settings.iam_data.resources.get_resource_type_details(resource.service, resource.resource_type)
        # TODO: also need to handle relationship

        # TODO: arn matching here is very simplistic. does not handle wildcard expansion/regexes
        #       might be possible to use Cypher regexes (i think apeman does this?)
        session.run(f"""MERGE (n{{arn:"{str(resource)}"}})""")

    else:
        raise Exception(f'Resource "{str(resource)}" not valid ARN for service')
