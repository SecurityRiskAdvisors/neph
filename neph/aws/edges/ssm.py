from ..nodes.ssm import SsmManagedInstance
from ..nodes.ec2 import EC2Instance

from ...edges import BasicRelationship


class SsmManagedEC2Instance(BasicRelationship):
    """
    Relates an IAM Identity Center group to its parent Identity Center instance
    """

    start = SsmManagedInstance
    end = EC2Instance
    start_property = "instance_id"
    end_property = "instance_id"
    relation = "SSM_MANAGED"

    account_match = True
