from ...nodes import BaseGraphNode


class VpcSecurityGroup(BaseGraphNode):
    table = "aws_vpc_security_group"
    id = "arn"
    label = "VpcSecurityGroup"


class Vpc(BaseGraphNode):
    table = "aws_vpc"
    id = "arn"
    label = "Vpc"


class EC2KeyPair(BaseGraphNode):
    table = "aws_ec2_key_pair"
    id = "key_pair_id"
    label = "EC2KeyPair"


class EC2Instance(BaseGraphNode):
    table = "aws_ec2_instance"
    id = "arn"
    label = "EC2Instance"


class VpcSubnet(BaseGraphNode):
    table = "aws_vpc_subnet"
    id = "subnet_arn"
    label = "VpcSubnet"


class VpcRouteTable(BaseGraphNode):
    table = "aws_vpc_route_table"
    id = "route_table_id"
    label = "VpcRouteTable"


class VpcNatGateway(BaseGraphNode):
    table = "aws_vpc_nat_gateway"
    id = "arn"
    label = "VpcNatGateway"


class VpcInternetGateway(BaseGraphNode):
    table = "aws_vpc_internet_gateway"
    id = "internet_gateway_id"
    label = "VpcInternetGateway"


class VpcEndpoint(BaseGraphNode):
    table = "aws_vpc_endpoint"
    id = "vpc_endpoint_id"
    label = "VpcEndpoint"


class VpcNetworkInterface(BaseGraphNode):
    table = "aws_ec2_network_interface"
    id = "network_interface_id"
    label = "VpcNetworkInterface"
