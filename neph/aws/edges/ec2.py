from neo4j import Session

from ...db import add_session
from ...edges import BasicRelationship
from ...leads import BaseLead

from ..nodes.ec2 import (
    EC2KeyPair,
    EC2Instance,
    Vpc,
    VpcSecurityGroup,
    VpcRouteTable,
    VpcNatGateway,
    VpcSubnet,
    VpcEndpoint,
    VpcInternetGateway,
    VpcNetworkInterface,
)
from ..nodes.iam import IamInstanceProfile


class EC2InstanceAssumeInstanceProfile(BasicRelationship):
    """
    Relates EC2 instances to their instance profiles
    """

    start = EC2Instance
    end = IamInstanceProfile
    start_property = "iam_instance_profile_arn"
    end_property = "arn"
    relation = "CAN_ASSUME"


class EC2KeyCanSSH(BasicRelationship):
    """
    Relates EC2 SSH key pairs to the instances they can access
    based on the instance properties
    """

    start = EC2KeyPair
    end = EC2Instance
    start_property = "key_name"
    end_property = "key_name"
    relation = "CAN_SSH"

    @classmethod
    def query(cls) -> str:
        # need to also match on region+account since the instance node only tracks the key name
        return f"""
        MATCH (start:{cls.start.label})
        MATCH (end:{cls.end.label})
        WHERE start.{cls.start_property} = end.{cls.end_property} and start.region = end.region and start.account_id = end.account_id
        MERGE (start)-[:{cls.relation}]->(end)
        """


# TODO: ENI -> EC2Instance, ENI -> Subnet, VpcSecurityGroup -> ENI, EIP -> ENI/EIP -> EC2Instance


class EC2WithinSubnet(BasicRelationship):
    """
    Relates EC2 instances to their parent subnet
    """

    start = EC2Instance
    end = VpcSubnet
    start_property = "subnet_id"
    end_property = "subnet_id"
    relation = "WITHIN"


# TODO: Security group -> ENI
#       "groups": "[{\"GroupId\":\"sg-01234abc\" ...}]",
class InterfaceWithinSubnet(BasicRelationship):
    """
    Relates network instances to their parent subnet
    """

    start = VpcNetworkInterface
    end = VpcSubnet
    start_property = "subnet_id"
    end_property = "subnet_id"
    relation = "WITHIN"


class InterfaceAttachedToInstance(BasicRelationship):
    """
    Relates EC2 instance to their attached network interfaces
    """

    start = VpcNetworkInterface
    end = EC2Instance
    start_property = "attached_instance_id"
    end_property = "instance_id"
    relation = "ATTACHED"


class SecurityGroupWithinVpc(BasicRelationship):
    """
    Relates security groups to their parent VPC
    """

    start = VpcSecurityGroup
    end = Vpc
    start_property = "vpc_id"
    end_property = "vpc_id"
    relation = "WITHIN"


class SubnetWithinVpc(BasicRelationship):
    """
    Relates subnets to their parent VPC
    """

    start = VpcSubnet
    end = Vpc
    start_property = "vpc_id"
    end_property = "vpc_id"
    relation = "WITHIN"


class RouteTableWithinSubnet(BasicRelationship):
    """
    Relates route tables to their parent VPC
    """

    start = VpcRouteTable
    end = VpcSubnet
    start_property = "associations"
    end_property = "subnet_id"
    relation = "WITHIN"

    @classmethod
    def query(cls) -> str:
        return f"""
        MATCH (start:{cls.start.label})
        WITH *, apoc.convert.fromJsonList(start.associations) as associations
        UNWIND associations as association
        MATCH (end:{cls.end.label}{{subnet_id: association.SubnetId, account_id: start.account_id}})
        MERGE (start)-[:{cls.relation}]->(end)
        """


# TODO: ENI -> NatGW
#       "nat_gateway_addresses": "[{..."NetworkInterfaceId\":\"eni-01234abc\"...}]"
class NatGatewayWithinVpc(BasicRelationship):
    """
    Relates NAT gateways to their parent VPC
    """

    start = VpcNatGateway
    end = Vpc
    start_property = "vpc_id"
    end_property = "vpc_id"
    relation = "WITHIN"


class InternetGatewayWithinVpc(BasicRelationship):
    """
    Relates route tables to their parent VPC
    """

    start = VpcInternetGateway
    end = Vpc
    start_property = "attachments"
    end_property = "vpc_id"
    relation = "WITHIN"

    @classmethod
    def query(cls) -> str:
        return f"""
        MATCH (start:{cls.start.label})
        WITH *, apoc.convert.fromJsonList(start.attachments) as attachments
        UNWIND attachments as attachment
        MATCH (end:{cls.end.label}{{vpc_id: attachment.VpcId, account_id: start.account_id}})
        MERGE (start)-[:{cls.relation}]->(end)
        """


# TODO: no table for ec2 instance connect endpoints, need a table for DescribeInstanceConnectEndpoints -> new lead based on this one
class SsmEc2VpcLead(BaseLead):
    """
    Uses SSM VPC endpoints to generate leads for potential SSM access.
    Leads are created between the SSM service and EC2 instances in the
        same subnet as the VPC endpoint
    """

    nodes = [VpcEndpoint, EC2Instance]
    relation = "SSM_ACCESS"

    @classmethod
    @add_session()
    def populate(cls, session: Session = None):
        query = f"""
        MATCH (vpce:{VpcEndpoint.label})
        WHERE vpce.service_name CONTAINS 'ssmmessages' or vpce.service_name CONTAINS 'ec2messages'
        MATCH (ec2:{EC2Instance.label})
        WHERE ec2.subnet_id in vpce.subnet_ids
        MERGE (:Service{{key: "ssm"}})-[:LEAD{{type: "{cls.relation}"}}]->(ec2)
        """
