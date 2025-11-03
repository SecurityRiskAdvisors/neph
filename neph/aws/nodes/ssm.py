from ...nodes import BaseGraphNode


class SsmManagedInstance(BaseGraphNode):
    table = "aws_ssm_managed_instance"
    id = "arn"
    label = "SsmManagedInstance"
