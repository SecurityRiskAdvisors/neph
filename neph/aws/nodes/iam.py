from typing import List, Set
from neo4j import Session
import json

from .iic import IicInlinePolicy

from ..policies import get_allowed_services_from_policy, get_allowed_actions_from_policy, DIRECT_PRIVESC_PERMISSIONS

from ...db import add_session
from ...nodes import BaseGraphNode, FakeGraphNode
from ...enrich import NodeEnrichment
from ...reporting import PropertiesTable
from ...utils import cast_table_query
from ...settings import Settings
from ...log import logger


class IamInstanceProfile(FakeGraphNode):
    table = ""
    id = "arn"
    label = "IamInstanceProfile"

    @classmethod
    def columns(cls) -> List[str]:
        return ["arn"]


class IamInlinePolicy(FakeGraphNode):
    table = ""
    id = "name"
    label = "IamInlinePolicy"

    @classmethod
    def columns(cls) -> List[str]:
        return ["name", "policy", "principal_arn"]


class IamUser(BaseGraphNode):
    table = "aws_iam_user"
    id = "arn"
    label = "IamUser"


class IamGroup(BaseGraphNode):
    table = "aws_iam_group"
    id = "arn"
    label = "IamGroup"


class IamRole(BaseGraphNode):
    table = "aws_iam_role"
    id = "arn"
    label = "IamRole"


class IamPolicy(BaseGraphNode):
    table = "aws_iam_policy"
    id = "arn"
    label = "IamPolicy"

    # manage policies are pre-generated as fixture nodes,
    # so only need to collect customer managed policies
    table_query = cast_table_query("aws_iam_policy") + " where is_aws_managed = FALSE"


class IamAccessKey(BaseGraphNode):
    table = "aws_iam_access_key"
    id = "access_key_id"
    label = "IamAccessKey"


class IamSamlProvider(BaseGraphNode):
    table = "aws_iam_saml_provider"
    id = "arn"
    label = "IamSamlProvider"


class IamOidcProvider(BaseGraphNode):
    table = "aws_iam_open_id_connect_provider"
    id = "arn"
    label = "IamOidcProvider"


class IamPolicyNumberOfServices(NodeEnrichment):
    """
    Add the num_services (integer as string) property all policy nodes,
    which represents the number of services the policy allows interaction with
    Example: num_services: '10'
    """

    nodes = [IamPolicy, IamInlinePolicy, IicInlinePolicy]

    @classmethod
    @add_session()
    def enrich(cls, stub, session: Session = None):
        if hasattr(stub, "policy") and (policy := getattr(stub, "policy")) is not None:
            policy_json = json.loads(policy)

            allowed_services = get_allowed_services_from_policy(policy_json)
            num_services = len(allowed_services)

            parent = stub.get_parent()
            if parent == IamPolicy:
                match = f"""MATCH (policy:{IamPolicy.label}{{arn: "{stub.arn}"}})"""
            elif parent in [IamInlinePolicy, IicInlinePolicy]:
                match = f"""MATCH (policy:{IamInlinePolicy.label}|{IicInlinePolicy.label}{{principal_arn: "{stub.principal_arn}", name: "{stub.name}", policy: '{stub.policy}' }})"""
            else:
                return

            query = f"""
            {match}
            SET policy.num_services = toString($num_services)
            """
            session.run(query, parameters={"num_services": num_services})


class IamPolicyServiceAdmin(NodeEnrichment):
    """
    Adds the service_admin (string list as string) property to all
    policy nodes, which represents the services for which the
    policy grants all actions (e.g. ec2:*)
    Example: service_admin: '["ec2"]'
    """

    nodes = [IamPolicy, IamInlinePolicy, IicInlinePolicy]

    @classmethod
    @add_session()
    def enrich(cls, stub, session: Session = None):
        if hasattr(stub, "policy") and (policy := getattr(stub, "policy")) is not None:
            policy_json = json.loads(policy)

            allowed_actions = get_allowed_actions_from_policy(policy_json)
            allowed_actions_grouped = dict()
            for action in allowed_actions:
                service, _ = action.split(":")
                allowed_actions_grouped.setdefault(service, set()).add(action)

            admin_services = set()
            for service, actions in allowed_actions_grouped.items():  # type: str, Set[str]
                service_actions = Settings.iam_data.actions.get_actions_for_service(service)
                all_service_actions = set([f"{service}:{method}" for method in service_actions])

                intersection = actions.intersection(all_service_actions)
                if intersection == all_service_actions:
                    admin_services.add(service)

            if len(admin_services) > 0:
                parent = stub.get_parent()
                if parent == IamPolicy:
                    match = f"""MATCH (policy:{IamPolicy.label}{{arn: "{stub.arn}"}})"""
                elif parent in [IamInlinePolicy, IicInlinePolicy]:
                    match = f"""MATCH (policy:{IamInlinePolicy.label}|{IicInlinePolicy.label}{{principal_arn: "{stub.principal_arn}", name: "{stub.name}", policy: '{stub.policy}' }})"""
                else:
                    logger.warn(f'Node label "{parent.label}" not support for enrichment "{cls.__name__}"')
                    return

                admin_str = json.dumps(list(admin_services))
                query = f"""
                {match}
                SET policy.service_admin = '{admin_str}'
                """
                session.run(query)


class IamPolicyPrivescPermissions(NodeEnrichment):
    """
    Add the iam_privesc (boolean as string) property and the
    iam_privesc_permissions (string list as string) property
    to all policy nodes.
    iam_privesc notes if the policy contains direct privesc permissions
    and iam_privesc_permissions contains the list of those permissions.
    Example:
        iam_privesc: 'True'
        iam_privesc_permissions: '["iam:AttachRolePolicy"]'
    """

    nodes = [IamPolicy, IamInlinePolicy, IicInlinePolicy]

    @classmethod
    @add_session()
    def enrich(cls, stub, session: Session = None):
        if hasattr(stub, "policy") and (policy := getattr(stub, "policy")) is not None:
            policy_json = json.loads(policy)

            allowed_actions = get_allowed_actions_from_policy(policy_json)

            # assume role should be handled already by leads
            # privesc = any([privesc_permission in allowed_actions for privesc_permission in DIRECT_PRIVESC_PERMISSIONS])
            privesc = list(filter(lambda x: x in DIRECT_PRIVESC_PERMISSIONS, allowed_actions))

            if len(privesc) > 0:
                parent = stub.get_parent()
                if parent == IamPolicy:
                    match = f"""MATCH (policy:{IamPolicy.label}{{arn: "{stub.arn}"}})"""
                elif parent in [IamInlinePolicy, IicInlinePolicy]:
                    match = f"""MATCH (policy:{IamInlinePolicy.label}|{IicInlinePolicy.label}{{principal_arn: "{stub.principal_arn}", name: "{stub.name}", policy: '{stub.policy}' }})"""
                else:
                    return

                permissions_str = json.dumps(privesc)
                query = f"""
                {match}
                SET policy.iam_privesc = "true"
                SET policy.iam_privesc_permissions = '{permissions_str}'
                """
                session.run(query)
