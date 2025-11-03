from neo4j import Session
import json

from ..principals import statement_to_match_queries
from ..nodes.iam import IamPolicy, IamInlinePolicy
from ..nodes.iic import IicInlinePolicy

from ...leads import BaseLead
from ...db import add_session
from ...nodes import BaseGraphNode, record_to_stub


class ResourcePolicyPrincipalLead(BaseLead):
    """
    Relates principals in resource policies to the resource
    """

    nodes = [BaseGraphNode]
    relation = "CAN_INTERACT"

    @classmethod
    @add_session()
    def populate(cls, session: Session = None):
        queries = []

        # query for all nodes that have a "policy" property but arent a policy object
        nodes = session.run(
            f"""MATCH (n) where n.policy is not null and not n:{IamPolicy.label} and not n:{IamInlinePolicy.label} and not n:{IicInlinePolicy.label} return n"""
        )
        for node in nodes:
            stub_node = record_to_stub(node[0])
            policy = json.loads(getattr(stub_node, "policy"))

            end_node = f"""MATCH (end) where elementId(end) = "{node[0].element_id}" """
            relation_properties = {"type": cls.relation}

            sub_queries = statement_to_match_queries(
                policy=policy, relation_properties=relation_properties, end_node=end_node, relation="LEAD"
            )
            queries.extend(sub_queries)

        for query in queries:
            session.run(query)
