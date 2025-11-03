from ...edges import AssocRelationship, BasicRelationship

from ..nodes.org import OrganizationPolicy, OrganizationalUnit, Organization, OrganizationAccount
from ..nodes.core import Account


class OrganizationPolicyAccountAttachments(AssocRelationship):
    """
    Relates an Organization policy to the Accounts it applies to
    """

    table = "aws_organizations_policy_target"
    start = OrganizationPolicy
    end = Account
    start_property = "arn"
    end_property = "account_id"
    start_rel_property = "arn"
    end_rel_property = "target_id"
    relation = "ATTACHED"

    def _data_query_from_sql(self):
        # TODO: implement
        raise NotImplementedError("Cannot generate edge from SQL")


class OrganizationOuParents(BasicRelationship):
    """
    Relates Organization OUs to other OUs
    """

    start = OrganizationalUnit
    end = OrganizationalUnit
    start_property = "parent_id"
    end_property = "id"
    relation = "WITHIN"


class OrganizationOuRoot(BasicRelationship):
    """
    Relates Organization OUs to the Organization root
    """

    start = OrganizationalUnit
    end = Organization
    start_property = "parent_id"
    end_property = "id"
    relation = "WITHIN"


class OrganizationOuChildren(BasicRelationship):
    """
    Relates AWS Organization accounts to their parent OUs
    """

    start = OrganizationAccount
    end = OrganizationalUnit
    start_property = "parent_id"
    end_property = "id"
    relation = "WITHIN"
