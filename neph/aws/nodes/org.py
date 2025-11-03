from ...nodes import BaseGraphNode


class OrganizationPolicy(BaseGraphNode):
    table = "aws_organizations_policy"
    id = "arn"
    types = ["SERVICE_CONTROL_POLICY", "RESOURCE_CONTROL_POLICY"]
    label = "OrganizationPolicy"


class Organization(BaseGraphNode):
    table = "aws_organizations_root"
    id = "arn"
    label = "Organization"


class OrganizationAccount(BaseGraphNode):
    table = "aws_organizations_account"
    id = "id"
    label = "OrganizationAccount"


class OrganizationalUnit(BaseGraphNode):
    table = "aws_organizations_organizational_unit"
    id = "arn"
    label = "OrganizationalUnit"
