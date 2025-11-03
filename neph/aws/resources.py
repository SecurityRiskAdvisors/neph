from typing import Tuple, List

from .policies import ActionString

from ..settings import Settings


type Resource = str
"""AWS API resource type name (ex: "bucket" for S3 Buckets)"""
type ResourceDetails = Tuple[Resource, dict]
"""Dict of a resource name and its details, such as the ARN format"""


def get_details_for_action(action: ActionString) -> List[ResourceDetails]:
    """
    For a given API action, get the corresponding resource type(s) and their details.
    E.g. iam:CreateUser -> user -> {<details>}
    """

    service, method = action.split(":")
    resource_types = Settings.iam_data.actions.get_action_details(service, method).get("resourceTypes", [])

    details = []
    for resource_type in resource_types:
        resource_name = resource_type.get("name")
        resource_details = Settings.iam_data.resources.get_resource_type_details(service, resource_name)
        details.append((resource_name, resource_details))

    return details
