import json
from typing import List, Set
from neo4j import Session

from .aws.nodes.core import Account
from .aws.nodes.org import OrganizationPolicy

from .aws.policies import ALLOW_ALL_BOUNDARY, ALLOW_ALL_RESOURCE, ALLOW_ALL_SCP
from .db import add_session
from .exceptions import NodeNotFound, LoggedException
from .log import logger
from .nodes import GraphNodeStubT, record_to_stub, get_stub_by_arn, get_stub_by_id

from .aws.nodes.iam import IamPolicy, IamInlinePolicy, IamGroup
from .utils import ARN


@add_session()
def get_attached_policies_for_stub(stub: GraphNodeStubT, session: Session = None) -> List[dict]:
    """
    Get all identity policies (managed, inline) attached to a given node
    """

    attached_policies: List[dict] = []
    attached_policies_query = f"""MATCH (n{{arn:"{stub.arn}"}})<-[:ATTACHED]-(policy:{IamPolicy.label}|{IamInlinePolicy.label}) return policy"""
    for attached_policy_node in session.run(attached_policies_query).values():
        attached_policy = record_to_stub(attached_policy_node[0], include_fakes=True)
        if attached_policy.policy:
            attached_policy_dict = json.loads(attached_policy.policy)
            attached_policies.append(attached_policy_dict)

    return attached_policies


def get_permission_boundary_policies_for_stub(stub: GraphNodeStubT) -> List[dict]:
    boundary_policies: List[dict] = []
    """
    Get all boundary policies attached to a given node
    """

    # permission boundary node property is a single policy ARN
    if (
        hasattr(stub, "permissions_boundary_arn")
        and (permissions_boundary_arn := getattr(stub, "permissions_boundary_arn")) != ""
    ):
        if permissions_boundary_arn and (boundary_policy := get_stub_by_arn(permissions_boundary_arn)):
            # boundary_policy = IamPolicy(**boundary_policy_node)
            if boundary_policy.policy:
                boundary_policy_dict = json.loads(boundary_policy.policy)
                boundary_policies.append(boundary_policy_dict)

    if len(boundary_policies) == 0:
        boundary_policy_dict = json.loads(ALLOW_ALL_BOUNDARY)
        boundary_policies.append(boundary_policy_dict)

    return boundary_policies


@add_session()
def get_groups_for_principal_stub(stub: GraphNodeStubT, session: Session = None) -> List[GraphNodeStubT]:
    """
    Get all groups the node is a member of
    """

    groups = []
    membership_query = f"""MATCH (n{{arn:"{stub.arn}"}})-[:MEMBER]->(group:{IamGroup.label}) return group"""
    group_nodes = session.run(membership_query).values()
    if len(group_nodes) > 0:
        for group_node in group_nodes[0]:
            group = record_to_stub(group_node)
            groups.append(group)

    return groups


def get_identity_policies_for_stub(stub: GraphNodeStubT, include_groups: bool = True) -> List[dict]:
    """
    Get all identity policies (managed, inline) attached to a given node as well
    as policies attached to any groups the node is a member of
    """

    identity_policies = []
    identity_policies.extend(get_attached_policies_for_stub(stub))
    if include_groups:
        for group in get_groups_for_principal_stub(stub):
            attached = get_attached_policies_for_stub(group)
            identity_policies.extend(attached)
    return identity_policies


def get_resource_policy_for_resource(resource: str | ARN) -> dict | None:
    """
    Get the resource policy on a given node
    """

    if isinstance(resource, str):
        resource = ARN.from_string(resource)

    resource_policy = None

    target_resource = None
    try:
        # first try to get the node by its arn
        main_node = get_stub_by_arn(resource)
    except NodeNotFound:
        if resource.resource_id:
            # but if that fails, try getting by the resources' parent
            # ex: arn:aws:s3:::mybucket/file.ext -> search for arn:aws:s3:::mybucket
            parent = resource.parent
            try:
                parent_node = get_stub_by_arn(arn=parent)
            except NodeNotFound:
                pass
            else:
                target_resource = parent_node
    else:
        target_resource = main_node

    if not target_resource:
        logger.warn(f'Cannot locate parent or child node for arn "{str(resource)}"')

    # TODO: add a "resource_policy" property to graph node to allow overriding the property?

    # assumes the resource policy property is called "policy". this seems accurate for common services like S3 and Lambda
    if hasattr(target_resource, "policy") and (policy := getattr(target_resource, "policy")):
        resource_policy = json.loads(policy)

    if hasattr(target_resource, "assume_role_policy") and (
        trust_policy := getattr(target_resource, "assume_role_policy")
    ):
        resource_policy = json.loads(trust_policy)

    if resource_policy:
        # need to add the resource key to the trust policy so it acts like a normal resource policy
        # https://github.com/cloud-copilot/iam-simulate/blob/92cdb1141764f3af84ce6725b77df3f085d39316/src/core_engine/coreEngineTests/sts/assumeRole/sameAccount.json#L117
        for statement in resource_policy.get("Statement"):
            if "Resource" not in statement:
                statement["Resource"] = str(resource)

    else:
        # resource_policy = json.loads(ALLOW_ALL_RESOURCE)
        resource_policy = None

    return resource_policy


# TODO: ou inheritance?
@add_session()
def get_scps_for_account(account_id: str, session: Session = None) -> List[dict]:
    """
    Get all organization SCPs attached to a given account
    """

    # this requires that the data collector run against the org

    add_default_scp = False
    scps_enabled = False
    sc_policies: List[dict] = []
    account = get_stub_by_id("aws_account", account_id)

    if hasattr(account, "organization_available_policy_types") and (
        organization_available_policy_types := getattr(account, "organization_available_policy_types")
    ):
        policy_settings = json.loads(organization_available_policy_types)

        # currently pulling this from account details but its also available on the org root node
        scp_settings: List[dict] = [
            setting for setting in filter(lambda x: x.get("Type") == "SERVICE_CONTROL_POLICY", policy_settings)
        ]

        if len(scp_settings) > 0:
            scps_enabled = scp_settings[0].get("Status") == "ENABLED"
    else:
        add_default_scp = True

    if scps_enabled:
        attached_sc_policies_query = f"""MATCH (n:{Account.label}{{account_id:"{account.account_id}"}})<-[:ATTACHED]-(policy:{OrganizationPolicy.label}{{type:"SERVICE_CONTROL_POLICY"}}) return policy"""
        attached_sc_policy_nodes = session.run(attached_sc_policies_query).values()
        if len(attached_sc_policy_nodes) == 0:
            add_default_scp = True
        else:
            for attached_sc_policy_node in attached_sc_policy_nodes:
                attached_sc_policy = record_to_stub(attached_sc_policy_node[0])
                if attached_sc_policy.content:
                    attached_sc_policy_dict = json.loads(attached_sc_policy.content)
                    sc_policies.append(attached_sc_policy_dict)
    else:
        add_default_scp = True

    if add_default_scp:
        allow_all_scp = json.loads(ALLOW_ALL_SCP)
        sc_policies.append(allow_all_scp)

    return sc_policies


@add_session()
def get_rcps_for_account(account_id: str, session: Session = None) -> List[dict]:
    """
    Get all organization RCPs attached to a given account
    """

    # this requires that the data collector run against the org

    rcps_enabled = False
    rc_policies: List[dict] = []

    account = get_stub_by_id("aws_account", account_id)

    if hasattr(account, "organization_available_policy_types") and (
        organization_available_policy_types := getattr(account, "organization_available_policy_types")
    ):
        policy_settings = json.loads(organization_available_policy_types)

        # currently pulling this from account details but its also available on the org root node
        rcp_settings: List[dict] = [
            setting for setting in filter(lambda x: x.get("Type") == "RESOURCE_CONTROL_POLICY", policy_settings)
        ]

        if len(rcp_settings) > 0:
            rcps_enabled = rcp_settings[0].get("Status") == "ENABLED"

    if rcps_enabled:
        attached_rc_policies_query = f"""MATCH (n:{Account.label}{{account_id:"{account_id}"}})<-[:ATTACHED]-(policy:{OrganizationPolicy.label}{{type:"RESOURCE_CONTROL_POLICY"}}) return policy"""
        attached_rc_policy_nodes = session.run(attached_rc_policies_query).values()
        if len(attached_rc_policy_nodes) > 0:
            for attached_rc_policy_node in attached_rc_policy_nodes:
                attached_rc_policy = record_to_stub(attached_rc_policy_node[0])
                if attached_rc_policy.content:
                    attached_rc_policy_dict = json.loads(attached_rc_policy.content)
                    rc_policies.append(attached_rc_policy_dict)

    return rc_policies


@add_session()
def get_org_id_for_account(account_id: str, session: Session = None) -> str:
    """
    Get the organization ID for a given account.
    If there are multiple possible options, return the first one.
    """
    query = f"""MATCH p=(n:OrganizationAccount{{account_id: "{account_id}" }})-[*1..]->(m:Organization) return m.arn limit 1"""
    result = session.run(query).values()

    if result:
        arn_str = result[0][0]
        # arn:aws:organizations::123456:root/o-abc/r-def'
        arn = ARN.from_string(arn_str)
    else:
        all_orgs = session.run("""MATCH (n:Organization) return n""").values()
        if len(all_orgs) == 1:
            logger.warn(
                f'Could not determine direct Organization master for account "{account_id}". Using only Organization node in graph.'
            )
            org_node = record_to_stub(all_orgs[0][0])
            arn = ARN.from_string(org_node.arn)

        else:
            raise LoggedException(f'Cannot determine Organization ID for account: "{account_id}"')

    # get 'o-abc'
    org_id = arn.resource_id.split("/")[0]
    return org_id


@add_session()
def get_transitive_roles_for_arn(arn: str | ARN, session: Session = None) -> Set[str]:
    """
    Given a starting ARN, find all IAM roles it has a direct assume role relationship with.
    Consider both CAN_ASSUME relationship types and leads with a type of CAN_ASSUME.
    """

    role_arns = set()

    if isinstance(arn, ARN):
        arn = str(arn)

    # this query looks for all CAN_ASSUME paths b/w the given start node
    # and an end target of a role
    # it currently looks at only direct relationships, mainly for performance reasons
    #   e.g. adding "*1.." to the relationship significantly increases query time,
    #   especially for leads
    #   however, the query is left in a way to easily support adding it back
    can_assume_query = f""" 
    MATCH p=(start{{arn:"{arn}"}})-[:CAN_ASSUME]->(target:IamRole)
    WITH start, nodes(p) as all_nodes
    UNWIND all_nodes as n
    WITH n, start
    WHERE n:IamRole and not n.arn = start.arn 
    RETURN distinct(n.arn)
    """
    leads_can_assume_query = f""" 
    MATCH p=(start{{arn:"{arn}"}})-[:LEAD]->(target:IamRole)
    WHERE all(r in relationships(p) where r.type = "CAN_ASSUME")
    WITH start, nodes(p) as all_nodes
    UNWIND all_nodes as n
    WITH n, start
    WHERE n:IamRole and not n.arn = start.arn 
    RETURN distinct(n.arn)
    """

    for assumable_target in session.run(can_assume_query).values():
        role_arn = assumable_target[0]
        role_arns.add(role_arn)
    for assumable_target in session.run(leads_can_assume_query).values():
        role_arn = assumable_target[0]
        role_arns.add(role_arn)

    return set(role_arns)
