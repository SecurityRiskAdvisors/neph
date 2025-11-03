from typing import List

from ...nodes import BaseGraphNode, FakeGraphNode


class IicPermissionSet(BaseGraphNode):
    table = "aws_ssoadmin_permission_set"
    id = "arn"
    label = "IicPermissionSet"


class IicInstance(BaseGraphNode):
    table = "aws_ssoadmin_instance"
    id = "arn"
    label = "IicInstance"


class IicUser(BaseGraphNode):
    table = "aws_identitystore_user"
    id = "id"
    label = "IicUser"


class IicGroup(BaseGraphNode):
    table = "aws_identitystore_group"
    id = "id"
    label = "IicGroup"


class IicInlinePolicy(FakeGraphNode):
    table = ""
    id = "name"  # added by relationship since these do not actually have names
    label = "IicInlinePolicy"

    @classmethod
    def columns(cls) -> List[str]:
        return ["name", "policy", "principal_arn"]
