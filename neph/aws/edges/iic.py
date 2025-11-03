from neo4j import Session

from ..nodes.iic import IicGroup, IicInstance, IicPermissionSet, IicUser, IicInlinePolicy
from ..nodes.org import OrganizationAccount
from ..nodes.iam import IamPolicy, IamRole

from ...edges import BasicRelationship, AssocRelationship
from ...leads import BaseLead
from ...db import add_session


class IicGroupWithinInstance(BasicRelationship):
    """
    Relates an IAM Identity Center group to its parent Identity Center instance
    """

    start = IicGroup
    end = IicInstance
    start_property = "identity_store_id"
    end_property = "identity_store_id"
    relation = "WITHIN"


class IicUserWithinInstance(BasicRelationship):
    """
    Relates an IAM Identity Center user to its parent Identity Center instance
    """

    start = IicUser
    end = IicInstance
    start_property = "identity_store_id"
    end_property = "identity_store_id"
    relation = "WITHIN"


class IicPermissionSetWithinInstance(BasicRelationship):
    """
    Relates an IAM Identity Center permission set to its parent Identity Center instance
    """

    start = IicPermissionSet
    end = IicInstance
    start_property = "instance_arn"
    end_property = "arn"
    relation = "WITHIN"


class IicUserGroupMember(AssocRelationship):
    """
    Relates an IAM Identity Center user to their groups
    """

    table = "aws_identitystore_group_membership"
    start = IicUser
    end = IicGroup
    start_property = "id"
    end_property = "id"
    start_rel_property = "member_id"
    end_rel_property = "group_id"
    relation = "MEMBER"


class IicPermissionSetGroupAssignment(AssocRelationship):
    """
    Relates an IAM Identity Center group to their assigned accounts
    """

    table = "aws_ssoadmin_account_assignment"
    start = IicGroup
    end = OrganizationAccount
    start_property = "id"
    end_property = "id"
    start_rel_property = "principal_id"
    end_rel_property = "target_account_id"
    relation = "PROVISIONED"

    relation_properties = {"permission_set_arn": "r.permission_set_arn"}


class IicPermissionSetUserAssignment(AssocRelationship):
    """
    Relates an IAM Identity Center user to their assigned accounts
    """

    table = "aws_ssoadmin_account_assignment"
    start = IicUser
    end = OrganizationAccount
    start_property = "id"
    end_property = "id"
    start_rel_property = "principal_id"
    end_rel_property = "target_account_id"
    relation = "PROVISIONED"

    relation_properties = {"permission_set_arn": "r.permission_set_arn"}


class IicPermissionSetPolicyAttachments(AssocRelationship):
    """
    Relates an IAM Identity Center permission set to their attached policies
    """

    table = "aws_ssoadmin_managed_policy_attachment"
    start = IamPolicy
    end = IicPermissionSet
    start_property = "arn"
    end_property = "arn"
    start_rel_property = "managed_policy_arn"
    end_rel_property = "permission_set_arn"
    relation = "ATTACHED"


class IicPermissionSetRoleProjectionLead(BaseLead):
    """
    Relates Identity Center permission sets to instances of the permission set inside a member account
    by looking for naming similarities between the permission set name and IAM roles.
    Typically, permission sets get projected into member account(s) as IAM roles and the role names follow
    the convention: AWSReservedSSO_<permission set name>_<random string>".
    """

    nodes = [IamRole, IicPermissionSet]
    relation = "PROJECTION"

    @classmethod
    @add_session()
    def populate(cls, session: Session = None):

        query = f"""
        MATCH (start:{IicPermissionSet.label})
        MATCH (end:{IamRole.label})
        WHERE end.name =~ "AWSReservedSSO_" + start.name + "_.*"
        MERGE (start)-[:LEAD{{type: "{cls.relation}"}}]->(end)
        """
        session.run(query)


class ExtractInlinePoliciesFromPermissionSets(BasicRelationship):
    """
    Create a relationship between a permission set and its inline policy after upserting the inline policy node.
    Unlike IAM roles/users/groups, permission set inline policies do not have names, so inline policies
    upserted by this class use a static name of "inline_policy".
    """

    start = IicInlinePolicy
    end = IicPermissionSet
    relation = "ATTACHED"
    start_property = "principal_arn"
    end_property = "arn"

    @classmethod
    def query(cls) -> str:
        # this is similar to edges.iam.unwind_inline_pols_to_nodes
        # but it does not require unrolling the policies since
        # permission sets can only have 1 inline policy
        #
        # permission set inline policies do not have names so
        # this also makes the policy name always "inline_policy"
        # to provide a consistent interface to IamInlinePolicy nodes
        return f"""
        MATCH (end:{cls.end.label})
        WHERE end.inline_policy is not null
        MERGE (start:{cls.start.label}{{principal_arn: end.arn, name: "inline_policy", policy: end.inline_policy }})
        MERGE (start)-[:{cls.relation}]->(end)
        """
