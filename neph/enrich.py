from abc import abstractmethod, ABC
from typing import List, TypeVar, Type
from neo4j import Session

from .db import add_session
from .nodes import BaseGraphNodeT, BaseGraphNode, GraphNodeStubT, record_to_stub
from .utils import get_subclasses
from .log import logger


class NodeEnrichment(ABC):
    """
    Base enrich class.

    Unlike other classes, enrichments work against node *stubs*, which means
    they are processed on the controller (host running Neph) rather than in Neo4j.
    They are intended to be used for more complex processing logic and/or integrating
    with other data sources. For example, processing IAM policy contents.
    """

    nodes: List[BaseGraphNodeT] = [BaseGraphNode]

    @classmethod
    @abstractmethod
    def enrich(cls, stub: GraphNodeStubT):
        pass


def enrich_node(stub: GraphNodeStubT):
    """
    Run all available enrichments on a given stub
    """

    node_type = stub.get_parent()
    for subclass in get_subclasses(NodeEnrichment):
        # same ideas as analysis.py's generate leads
        if node_type in subclass.nodes or BaseGraphNode in subclass.nodes:
            try:
                subclass.enrich(stub)
            except Exception as e:
                logger.warn(f'Error for enrichment "{subclass.__name__}" ({e})')


@add_session()
def bulk_enrich(node: BaseGraphNodeT, session: Session = None):
    """
    Run all available enrichments on a given node type after loading them into stubs
    """

    query = f"""MATCH (n:{node.label}) return n"""
    results = session.run(query).values()

    for result in results:
        stub = record_to_stub(result[0], include_fakes=True)
        enrich_node(stub)


NodeEnrichmentT = TypeVar("NodeEnrichmentT", bound=Type[NodeEnrichment])


def enrichments() -> List[NodeEnrichmentT]:
    return list(get_subclasses(NodeEnrichment))
