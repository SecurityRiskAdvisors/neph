from enum import Enum, auto
from typing import List, Tuple, Any
import re

from ..utils import ARN
from ..exceptions import Unsupported
from ..log import logger
from ..db import QueryWithParameters, CypherQuery

from .nodes.core import Account, Service, Wildcard


class PrincipalType(Enum):
    """
    AWS principal types that appear in policies
    """

    Standard = auto()
    Account = auto()
    IdP = auto()
    ExternalIdP = auto()
    Service = auto()
    Wildcard = auto()


# https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html#identifiers-unique-ids
UNIQUE_ID_PREFIXES = [
    "ABIA",  # AWS STS service bearer token
    "ACCA",  # Context-specific credential
    "AGPA",  # User group
    "AIDA",  # IAM user
    "AIPA",  # Amazon EC2 instance profile
    "AKIA",  # Access key
    "ANPA",  # Managed policy
    "ANVA",  # Version in a managed policy
    "APKA",  # Public key
    "AROA",  # Role
    "ASCA",  # Certificate
    "ASIA",  # Temporary (AWS STS) access key IDs use this prefix, but are unique only in combination with the secret access key and the session token.
]


def format_principal_str_or_arn(principal: str | ARN) -> Tuple[ARN, ARN | None]:
    """
    Resolve the given value to an "ARN" and resolve temporary ARN types to
    permanent ARN types (e.g. assumed roles -> roles)
    """

    if isinstance(principal, str):
        principal = ARN.from_string(principal)

    original_principal = None

    # convert assumed role to standard role
    # as assumed roles are not persistent resources
    if principal.resource_type == "assumed-role":
        original_principal = principal

        role_name = principal.resource_id.split("/")[0]
        principal = ARN(
            prefix=principal.prefix,
            partition=principal.partition,
            service="iam",  # sts -> iam
            region=principal.region,
            account_id=principal.account_id,
            resource_type="role",  # assumed-role -> role
            resource_id=role_name,
        )

    return principal, original_principal


def get_principals_from_dict(principal_dict: dict | str) -> List[Tuple[PrincipalType, Any]]:
    """
    Given the "Principal" section from a policy, return a list of principal types + ARNs (as a tuple) or other IDs

    For Wildcard types, the value is always "*". For ExternalIdP types, the value is the IdP domain (ex "accounts.google.com"). For Service types, the value is the service ID (ex ec2.amazonaws.com). Note: this can be either the regionalized (<service>.<region>.amazonaws.com) OR nonregionalized (<service>.<region>.amazonaws.com) form of the ID.
    """
    results = []

    if isinstance(principal_dict, str):
        if principal_dict == "*":
            results = [(PrincipalType.Wildcard, "*")]
            return results

    for key, properties in principal_dict.items():
        if not isinstance(properties, list):
            principals = [properties]
        else:
            principals = properties

        match key:
            # https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html
            case "AWS":
                for principal in principals:  # type: str

                    # TODO: need to handle iam user to user id conversion?
                    #  (https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html#principal-users)

                    if principal.startswith("arn"):
                        arn = ARN.from_string(principal)

                        if arn.service == "iam" and arn.resource_type == "root":
                            # arn:aws:iam::12345:root" -> is an alt for of specifying the account id
                            # e.g. allowing sts:AssumeRole from it will allow all principals in the account
                            results.append((PrincipalType.Account, arn))
                        else:
                            results.append((PrincipalType.Standard, arn))

                    elif principal == "*":
                        results.append((PrincipalType.Wildcard, "*"))

                    elif principal[:4] in UNIQUE_ID_PREFIXES:
                        # TODO: worth trying to resolve unique IDs to accounts/arns?
                        continue

                    elif re.match("[0-9]{12}", principal) is not None:
                        # short form version of the account id principal
                        arn = ARN(account_id=principal)
                        results.append((PrincipalType.Account, arn))

                    else:
                        # TODO: not sure if there are any forms other than account ID or ARN that need to be handled here
                        continue

            case "CanonicalUser":
                # TODO: only for resource policies
                raise Unsupported("CanonicalUser principal type not supported")

            case "Federated":
                for principal in principals:
                    if principal.startswith("arn"):
                        # example: an IAM-managed SAML IdP
                        arn = ARN.from_string(principal)
                        results.append((PrincipalType.IdP, arn))
                    else:
                        # example: 3rd party OIDC
                        results.append((PrincipalType.ExternalIdP, principal))

            case "Service":
                for principal in principals:
                    # this is either non-regionalized or regionalized form
                    results.append((PrincipalType.Service, principal))

            case _:
                raise Exception(f'Unknown principal type: "{key}"')

    return results


def principal_to_match_stmt(principal_type: PrincipalType, principal_id) -> QueryWithParameters:
    """
    Convert a principal to a Cypher MATCH statement
    """

    extra_properties = {}
    match_stmt = None

    match principal_type:
        case PrincipalType.Standard | PrincipalType.IdP:
            principal_id: ARN

            # convert role sessions to roles since assumed roles are not persistent nodes
            if principal_id.resource_type == "assumed-role":
                role_name_parts = principal_id.resource_id.split("/")
                principal_id, _ = format_principal_str_or_arn(principal_id)
                extra_properties["role_session_name"] = "/".join(role_name_parts[1:])

            match_stmt = f"""MATCH (start{{arn:"{str(principal_id)}"}})"""

        case PrincipalType.Account:
            principal_id: ARN
            # merge here for when these are new account (e.g. in a trust policy)

            # ffr: WITH <node> required after MERGE unlike after MATCH
            match_stmt = f"""MERGE (start:{Account.label}{{account_id:"{principal_id.account_id}"}}) WITH start"""

        case PrincipalType.ExternalIdP:
            # TODO
            logger.warn("Extenal IdP principal type not yet implemented. Skipping...")

        case PrincipalType.Service:
            principal_id: str
            service_key = principal_id.split(".")[0].lower()
            match_stmt = f"""MATCH (start:{Service.label}{{key:"{service_key}"}})"""

        case PrincipalType.Wildcard:
            match_stmt = f"""MATCH (start:{Wildcard.label})"""

        case _:
            pass

    return match_stmt, extra_properties


def statement_to_match_queries(
    policy: dict, relation_properties: dict, end_node: str, relation: str
) -> List[CypherQuery]:
    """
    Convert the statements from a policy into Cypher queries based on it principals
    """

    queries = []
    for statement in policy.get("Statement"):
        if (principal_dict := statement.get("Principal", None)) is None:
            continue
        try:
            principals = get_principals_from_dict(principal_dict)
        except Unsupported:
            continue

        for principal_type, principal_id in principals:
            start_node, extra_rel_props = principal_to_match_stmt(principal_type, principal_id)
            relation_properties = {**extra_rel_props, **relation_properties}

            if start_node:
                relationship = f"""r:{relation}{{"""
                relationship += ", ".join([f'{k}:"{v}"' for k, v in relation_properties.items()])
                relationship += "}"

                query = f"""{start_node}
                {end_node}
                MERGE (start)-[{relationship}]->(end)
                """
                queries.append(query)

    return queries
