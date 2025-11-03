from neo4j import Session
import json

from ..principals import statement_to_match_queries
from ..nodes.iam import IamPolicy, IamRole, IamGroup, IamUser, IamInstanceProfile, IamAccessKey, IamInlinePolicy

from ...edges import BasicRelationship, jsonlist_query_unroll_end
from ...leads import BaseLead
from ...db import add_session


class IamRolePolicyAttachments(BasicRelationship):
    """
    Relates an IAM policy to the roles its attached to
    """

    start = IamPolicy
    end = IamRole
    relation = "ATTACHED"
    start_property = "arn"
    end_property = "attached_policy_arns"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.start.label,
            end_label=cls.end.label,
            start_property=cls.start_property,
            end_property=cls.end_property,
            relation="ATTACHED",
        )


class IamGroupPolicyAttachments(BasicRelationship):
    """
    Relates an IAM policy to the groups its attached to
    """

    start = IamPolicy
    end = IamGroup
    relation = "ATTACHED"
    start_property = "arn"
    end_property = "attached_policy_arns"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.start.label,
            end_label=cls.end.label,
            start_property=cls.start_property,
            end_property=cls.end_property,
            relation="ATTACHED",
        )


class IamUserPolicyAttachments(BasicRelationship):
    """
    Relates an IAM policy to the users its attached to
    """

    start = IamPolicy
    end = IamUser
    relation = "ATTACHED"
    start_property = "arn"
    end_property = "attached_policy_arns"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.start.label,
            end_label=cls.end.label,
            start_property=cls.start_property,
            end_property=cls.end_property,
            relation="ATTACHED",
        )


class IamUserGroups(BasicRelationship):
    """
    Relates an IAM user to their groups
    """

    start = IamUser
    end = IamGroup
    relation = "MEMBER"
    start_property = "groups"
    end_property = "arn"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.end.label,
            end_label=cls.start.label,
            start_property=cls.end_property,
            end_property=cls.start_property,
            relation=cls.relation,
            nested_end_property="Arn",
            invert_rel_direction=True,
        )


class ExtractInstanceProfilesFromRoles(BasicRelationship):
    """
    Relates EC2 instance profiles to their connected IAM role
    """

    start = IamInstanceProfile
    end = IamRole
    relation = "INSTANCE_PROFILE"
    start_property = "arn"
    end_property = "arn"

    @classmethod
    def query(cls) -> str:
        return f"""
        MATCH (end:{cls.end.label})
        WITH *, apoc.convert.fromJsonList(end.instance_profile_arns) as instance_profile_arns_list
        UNWIND instance_profile_arns_list as instance_profile_arns_item
        MERGE (start:{cls.start.label}{{arn: instance_profile_arns_item }})
        MERGE (start)-[:{cls.relation}]->(end)
        """


def unwind_inline_pols_to_nodes(start_node: str, end_node: str, relation: str):
    """
    For nodes with an inline_policies property, deserialize that property then upsert nodes
    for each inline policy and establish an edge between the original node and the new nodes.
    """

    return f"""
        MATCH (end:{end_node})
        WHERE end.inline_policies is not null
        WITH *, apoc.convert.fromJsonList(end.inline_policies) as inline_policies_list
        UNWIND inline_policies_list as inline_policy
        MERGE (start:{start_node}{{principal_arn: end.arn, name: inline_policy.PolicyName, policy: apoc.convert.toJson(inline_policy.PolicyDocument) }})
        MERGE (start)-[:{relation}]->(end)
        """


class ExtractInlinePoliciesFromRoles(BasicRelationship):
    """
    Create a relationship between an IAM role and its inline policies after upserting the inline policy nodes
    """

    start = IamInlinePolicy
    end = IamRole
    relation = "ATTACHED"
    start_property = "principal_arn"
    end_property = "arn"

    @classmethod
    def query(cls) -> str:
        return unwind_inline_pols_to_nodes(start_node=cls.start.label, end_node=cls.end.label, relation=cls.relation)


class ExtractInlinePoliciesFromUsers(BasicRelationship):
    """
    Create a relationship between an IAM user and its inline policies after upserting the inline policy nodes
    """

    start = IamInlinePolicy
    end = IamUser
    relation = "ATTACHED"
    start_property = "principal_arn"
    end_property = "arn"

    @classmethod
    def query(cls) -> str:
        return unwind_inline_pols_to_nodes(start_node=cls.start.label, end_node=cls.end.label, relation=cls.relation)


class ExtractInlinePoliciesFromGroups(BasicRelationship):
    """
    Create a relationship between an IAM group and its inline policies after upserting the inline policy nodes
    """

    start = IamInlinePolicy
    end = IamGroup
    relation = "ATTACHED"
    start_property = "principal_arn"
    end_property = "arn"

    @classmethod
    def query(cls) -> str:
        return unwind_inline_pols_to_nodes(start_node=cls.start.label, end_node=cls.end.label, relation=cls.relation)


class IamUserAccessKeys(BasicRelationship):
    """
    Relates an IAM user to their access keys
    """

    start = IamAccessKey
    end = IamUser
    relation = "CREDENTIAL"
    start_property = "user_name"
    end_property = "name"

    # TODO: username paths handled okay?
    @classmethod
    def query(cls) -> str:
        # need to add the account id in the condition
        # since the access key table does not include the
        # iam user arn
        return f"""
        MATCH (start:{cls.start.label})
        MATCH (end:{cls.end.label})
        WHERE start.{cls.start_property} = end.{cls.end_property} and start.account_id = end.account_id
        MERGE (start)-[:{cls.relation}]->(end)
        """


# TODO: handle IamUser.user_id = Principal: AIDAXXXX
class RoleTrustPolicyLead(BaseLead):
    """
    Relates principals in role trust policies to the role
    """

    nodes = [IamRole]
    relation = "CAN_ASSUME"

    @classmethod
    @add_session()
    def populate(cls, session: Session = None):
        queries = []
        role_nodes = session.run(f"""MATCH (node:{IamRole.label}) return node""").values()
        for role_node in role_nodes:
            role = IamRole.stub(data=role_node[0])
            trust_policy = json.loads(role.assume_role_policy)

            end_node = f"""MATCH (end:{IamRole.label}{{arn:"{role.arn}"}})"""
            relation_properties = {"type": cls.relation}

            sub_queries = statement_to_match_queries(
                policy=trust_policy, relation_properties=relation_properties, end_node=end_node, relation="LEAD"
            )
            queries.extend(sub_queries)

        for query in queries:
            session.run(query)
