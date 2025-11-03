from ...edges import BasicRelationship, jsonlist_query_unroll_end

from ..nodes.ec2 import VpcSubnet, VpcSecurityGroup
from ..nodes.rds import RdsInstance, RdsCluster, RdsSubnetGroup
from ..nodes.iam import IamRole
from ..nodes.secretsmanager import SecretsManagerSecret


class RdsInstanceInCluster(BasicRelationship):
    """
    Relates RDS instances to their parent clusters
    """

    start = RdsInstance
    end = RdsCluster
    start_property = "db_cluster_identifier"
    end_property = "db_cluster_identifier"
    relation = "WITHIN"
    account_match = True


class RdsClusterInSubnetGroup(BasicRelationship):
    """
    Relates RDS cluster to their networking subnet groups
    """

    start = RdsCluster
    end = RdsSubnetGroup
    start_property = "db_subnet_group"
    end_property = "name"
    relation = "WITHIN"
    account_match = True


class RdsSubnetGroupInVpcSubnet(BasicRelationship):
    """
    Relates RDS subnet groups to their parent VPC subnets
    """

    start = RdsSubnetGroup
    end = VpcSubnet
    start_property = "subnets"
    end_property = "subnet_id"
    relation = "WITHIN"
    account_match = True

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.end.label,
            end_label=cls.start.label,
            start_property=cls.end_property,
            end_property=cls.start_property,
            relation=cls.relation,
            nested_end_property="SubnetIdentifier",
            invert_rel_direction=True,
        )


class SecurityGroupAttachedToRdsCluster(BasicRelationship):
    """
    Relates RDS clusters with their attached network security groups
    """

    start = VpcSecurityGroup
    end = RdsCluster
    start_property = "group_id"
    end_property = "vpc_security_groups"
    relation = "ATTACHED"
    account_match = True

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.start.label,
            end_label=cls.end.label,
            start_property=cls.start_property,
            end_property=cls.end_property,
            relation=cls.relation,
            nested_end_property="VpcSecurityGroupId",
        )


class SecurityGroupAttachedToRdsInstance(BasicRelationship):
    """
    Relates RDS instances with their attached network security groups
    """

    start = VpcSecurityGroup
    end = RdsInstance
    start_property = "group_id"
    end_property = "vpc_security_groups"
    relation = "ATTACHED"
    account_match = True

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.start.label,
            end_label=cls.end.label,
            start_property=cls.start_property,
            end_property=cls.end_property,
            relation=cls.relation,
            nested_end_property="VpcSecurityGroupId",
        )


class RdsInstanceIamRoles(BasicRelationship):
    """
    Relates RDS instances with their attached IAM roles
    """

    start = RdsInstance
    end = IamRole
    relation = "CAN_ASSUME"
    end_property = "arn"
    start_property = "associated_roles"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            end_label=cls.start.label,
            start_label=cls.end.label,
            end_property=cls.start_property,
            start_property=cls.end_property,
            relation=cls.relation,
            nested_end_property="RoleArn",
            invert_rel_direction=True,
        )


class RdsClusterIamRoles(BasicRelationship):
    """
    Relates RDS clusters with their attached IAM roles
    """

    start = RdsCluster
    end = IamRole
    relation = "CAN_ASSUME"
    end_property = "arn"
    start_property = "associated_roles"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            end_label=cls.start.label,
            start_label=cls.end.label,
            end_property=cls.start_property,
            start_property=cls.end_property,
            relation=cls.relation,
            nested_end_property="RoleArn",
            invert_rel_direction=True,
        )


class SecretsManagerClusterAccess(BasicRelationship):
    """
    Related RDS clusters with their associated Secrets Manager secrets (SQL database user credentials)
    """

    start = SecretsManagerSecret
    end = RdsCluster
    start_property = "arn"
    end_property = "master_user_secret"
    relation = "SQL_ACCESS"

    @classmethod
    def query(cls) -> str:
        return jsonlist_query_unroll_end(
            start_label=cls.start.label,
            end_label=cls.end.label,
            start_property=cls.start_property,
            end_property=cls.end_property,
            relation=cls.relation,
            nested_end_property="SecretArn",
        )
