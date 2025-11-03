from ...edges import BasicRelationship, jsonlist_query_unroll_end

from ..nodes.iam import IamRole
from ..nodes.lambdaf import LambdaFunction
from ..nodes.ec2 import VpcSubnet, VpcSecurityGroup

# TODO:
#   lambda -> s3 (code archive), ecr (container lambda), etc


class LambdaFunctionAssumeRole(BasicRelationship):
    """
    Relates Lambda functions to their IAM roles
    """

    start = LambdaFunction
    end = IamRole
    start_property = "arn"
    end_property = "role"
    relation = "CAN_ASSUME"


class LambdaFunctionInVpcSubnet(BasicRelationship):
    """
    Relates Lambda functions to their parent VPC subnets
    """

    start = LambdaFunction
    end = VpcSubnet
    start_property = "vpc_subnet_ids"
    end_property = "subnet_id"
    relation = "WITHIN"
    account_match = True

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            end_label=cls.start.label,
            start_label=cls.end.label,
            end_property=cls.start_property,
            start_property=cls.end_property,
            relation=cls.relation,
            invert_rel_direction=True,
        )


class LambdaFunctionAttachedSecurityGroups(BasicRelationship):
    """
    Relates Lambda functions to their attached VPC security groups
    """

    start = VpcSecurityGroup
    end = LambdaFunction
    start_property = "vpc_security_group_ids"
    end_property = "group_id"
    relation = "ATTACHED"
    account_match = True

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            end_label=cls.end.label,
            start_label=cls.start.label,
            end_property=cls.end_property,
            start_property=cls.start_property,
            relation=cls.relation,
        )
