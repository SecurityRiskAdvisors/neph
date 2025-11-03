from neo4j import Session
from typing import List, TypeVar, Type
from abc import abstractmethod, ABC

from .db import add_session
from .utils import get_subclasses
from .nodes import BaseGraphNodeT, BaseGraphNode
from .log import logger
from .settings import Settings


class BaseLead(ABC):
    """
    Base lead class

    Leads are similar to relationships but meant to indicate the relationship requires
    additional analysis and should be considered unverified.
    Leads should be used to created relationships based on simple heuristics.
    All leads use the relationship type of LEAD and have a "type" property that specifies
    the sub-type of the lead.
    Promoting a lead converts the type from LEAD to the sub-type.
    """

    nodes: List[BaseGraphNodeT] = [BaseGraphNode]  # all nodes by default
    relation: str

    @classmethod
    @abstractmethod
    def populate(cls):
        pass


def generate_leads(node_types: List[BaseGraphNodeT] = None):
    """
    Generate all leads that involve on or more of the provided node types
    """

    if not Settings.generate_leads:
        return

    node_types = node_types if node_types else []

    populate = set()
    for subclass in get_subclasses(BaseLead):
        # this is the default from the base class
        # if its in the node list, the lead will apply to
        # all nodes
        if BaseGraphNode in subclass.nodes:
            populate.add(subclass)
        # otherwise only populate the leads that corresponds
        # to a provided node type
        else:
            for node_type in node_types:
                if node_type in subclass.nodes:
                    populate.add(subclass)

    for subclass in populate:
        try:
            subclass.populate()
        except Exception as e:
            logger.warn(f'Error for lead "{subclass.__name__}" ({e})')


BaseLeadT = TypeVar("BaseLeadT", bound=Type[BaseLead])


def leads() -> List[BaseLeadT]:
    return list(get_subclasses(BaseLead))
