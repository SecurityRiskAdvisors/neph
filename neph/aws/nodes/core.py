from typing import List
from neo4j import Session
import zipfile
import io
import json
from importlib.resources import path as resource_path

from .iam import IamPolicy

from ...nodes import BaseGraphNode, FakeGraphNode
from ...db import add_session
from ...settings import Settings
from ...reporting import PropertiesTable, unlabelled_report


# these fake node types either they dont map to a table or dont map to a real resource type
# but we still would like to represent them in code
class Wildcard(FakeGraphNode):
    """
    Node representing a blanket wildcard resource
    """

    table = ""
    id = "arn"
    label = "Wildcard"

    """
    @property
    def arn(self):
        return ARN.from_string("arn:aws:*:*:*:*")
    """

    @classmethod
    def columns(cls) -> List[str]:
        return ["name", "arn"]


class Service(FakeGraphNode):
    """
    Node representing an AWS service
    """

    table = ""
    id = "key"
    label = "Service"

    @classmethod
    def columns(cls) -> List[str]:
        return ["name", "key"]


class Account(BaseGraphNode):
    """
    Node representing an AWS account
    """

    table = "aws_account"
    id = "account_id"
    label = "Account"


@add_session()
def create_service_nodes(session: Session = None):
    """
    Create a service node for each available service
    """

    query = ""
    services = Settings.iam_data.services.get_service_keys()
    for i, service_key in enumerate(services):
        service_name = Settings.iam_data.services.get_service_name(service_key)
        query += Service.as_match(properties={"name": service_name, "key": service_key}, node_name=f"node{i}")
        query += "\n"

    session.run(query)


@add_session()
def create_wildcard_node(session: Session = None):
    """
    Create a node for blanket wildcards
    """

    query = Wildcard.as_match(
        properties={"name": "*", "arn": "arn:aws:*:*:*:*"},
    )
    session.run(query)


@add_session()
def create_policy_nodes(session: Session = None):
    """
    Create a node for each managed policy using data from https://github.com/iann0036/iam-dataset.
    This saves having to poll each account for policies, which is significant since there are >1000 managed policies.
    """

    with resource_path("neph", "data") as p:
        # zip of this project: https://github.com/iann0036/iam-dataset
        zipf_path = p / "policies.zip"
        zipf_bytes = zipf_path.read_bytes()

    policies = []
    # load the included zip file into memory
    # for each policy file in the managedpolicies directory, create a policy node
    zipf_bytes = io.BytesIO(zipf_bytes)
    with zipfile.ZipFile(zipf_bytes) as z:
        for zipi in z.infolist():
            if not zipi.is_dir() and zipi.filename.startswith("iam-dataset-main/aws/managedpolicies/"):
                with z.open(zipi) as f:
                    policy_data = f.read()
                    policy_data = json.loads(policy_data)
                    policy = {
                        "name": policy_data.get("name"),
                        "arn": policy_data.get("arn"),
                        "policy": json.dumps(policy_data.get("document")),
                        "is_aws_managed": "true",
                    }
                    policies.append(policy)

    query = f"""
    UNWIND $policies as policy
    MERGE (p:{IamPolicy.label}{{name: policy.name}})
    SET p=policy
    """
    session.run(query, parameters={"policies": policies})


def create_fixture_nodes():
    """
    Create all static nodes (service, wildcards, policies)
    """
    create_service_nodes()
    create_wildcard_node()
    create_policy_nodes()


class ExternalAccountReferences(PropertiesTable):
    """
    Get a list of resources with resource/assume role policies that reference account IDs not in the Organization
    """

    properties = ["id", "account", "policy"]
    node = BaseGraphNode

    @classmethod
    def query(cls):
        # this query does the following:
        # 1. find any node with a policy or assume_role_policy property except for policy nodes
        #       (finds things like resource policies)
        # 2. Pull out potential account numbers (12-digit numbers) from the policy
        # 3. Compare against the list of Org account IDs to filter to IDs not in an Org
        #       Have to use Org Account node types only since Account nodes are jit'd by base edges/leads
        # 4. Return remaining nodes
        return """
        MATCH (n) 
        WITH *, coalesce(n.policy, n.assume_role_policy) as policy
        WHERE policy is not null and not labels(n) in [['IamPolicy'], ['IamInlinePolicy'], ['IicInlinePolicy']]
        WITH *, apoc.text.regexGroups(policy, '(?<account>[0-9]{12})')[0] as accounts
        UNWIND accounts as account 
        WITH n, account, policy
        WHERE not account in COLLECT {MATCH (a:OrganizationAccount) RETURN a.id}
        RETURN coalesce(n.arn, n.id, elementId(n)) as id, account, policy
        """

    @classmethod
    def report(cls, *query_args, **query_kwargs):
        return unlabelled_report(query=cls.query(), properties=cls.properties)


class UnknownArns(PropertiesTable):
    """
    Get a list of resources with resource/assume role policies containing ARNs not in the graph.
    This report will likely have false positives. For example, account ARNs in the format
    "arn:aws:iam::123456:root" will be included even if the account is in the graph as the
    Account and OrganizationAccount nodes do not have ARNs.
    """

    properties = ["id", "arn", "policy", "account_id"]
    node = BaseGraphNode

    @classmethod
    def query(cls):
        # this query does the following:
        # 1. find any node with a policy or assume_role_policy property
        # 2. Pull out potential ARNs from the policy
        # 3. Compare against the list of all ARNs to filter to ARNs not in the graph
        # 4. Return remaining nodes

        # substring(arn_match, 0, size(arn_match)-1)
        # the regex match will include the ending quote from the pattern
        # so need to trim it off
        #   ex 'arn:aws:iam::123456:role/myrole"' -> 'arn:aws:iam::123456:role/myrole'
        #                                      ^here                          removed^
        return """
        MATCH (n) 
        WITH *, coalesce(n.policy, n.assume_role_policy) as policy
        WHERE policy is not null
        WITH *, apoc.text.regexGroups(policy, '(?<arn>arn:.*?")')[0] as arns
        UNWIND arns as arn_match
        WITH n, policy, substring(arn_match, 0, size(arn_match)-1) as arn
        WHERE not arn in COLLECT {MATCH (m) where m.arn is not null RETURN m.arn}
        RETURN coalesce(n.arn, n.id, elementId(n)) as id, arn, policy, n.account_id as account_id
        """

    @classmethod
    def report(cls, *query_args, **query_kwargs):
        return unlabelled_report(query=cls.query(), properties=cls.properties)
