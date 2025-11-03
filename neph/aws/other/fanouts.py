from ..policies import EC2_ACCESS_PERMISSIONS, DIRECT_PRIVESC_PERMISSIONS, CREDENTIAL_ACCESS_PERMISSIONS
from ..nodes.iam import IamRole

from ...fanout import PermissionsFanout, BruteForceFanout


class EC2AccessFanout(PermissionsFanout):
    """
    Fanout strategy to check for alternative EC2 access methods, namely
    SSM and EC2 instance connect actions.
    """

    permissions = EC2_ACCESS_PERMISSIONS


class CredentialAccessFanout(PermissionsFanout):
    """
    Fanout strategy to check for actions that can return any type of credential
    information.
    """

    permissions = CREDENTIAL_ACCESS_PERMISSIONS


class DirectPrivescFanout(PermissionsFanout):
    """
    Fanout strategy to check for actions that allow for direct privilege escalation
    """

    permissions = DIRECT_PRIVESC_PERMISSIONS


class AssumeRoleBruteForce(BruteForceFanout):
    """
    Fanout strategy to attempt role assumption of every role in the
    principals account.
    """

    resource = IamRole
    action = "sts:AssumeRole"
