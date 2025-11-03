from ...nodes import BaseGraphNode


class RdsCluster(BaseGraphNode):
    table = "aws_rds_db_cluster"
    id = "arn"
    label = "RdsCluster"


class RdsInstance(BaseGraphNode):
    table = "aws_rds_db_instance"
    id = "arn"
    label = "RdsInstance"


class RdsSubnetGroup(BaseGraphNode):
    table = "aws_rds_db_subnet_group"
    id = "arn"
    label = "RdsSubnetGroup"
