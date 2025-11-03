from typing import Tuple, Set
import fnmatch

from ..settings import Settings
from ..log import print_and_log, logger

type ActionString = str
"""AWS API action formatted like <api>:<method>"""

ALLOW_ALL_SCP = """
{
  "orgIdentifier": "ou-12345",
  "policies": [
    {
      "name": "AllowAll",
      "policy": {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": "*",
            "Resource": "*"
          }
        ]
      }
    }
  ]
}"""

ALLOW_ALL_BOUNDARY = """
{
    "PolicyName": "allowall",
    "PolicyDocument": {
        "Version": "2012-10-17", 
        "Statement": [
            {
                "Sid": "1", 
                "Action": "*", 
                "Effect": "Allow", 
                "Resource": "*"
            }
        ]
    }
}
"""

ALLOW_ALL_RESOURCE = """
{
    "Version": "2012-10-17", 
    "Statement": [
        {
            "Sid": "1", 
            "Action": "*", 
            "Effect": "Allow", 
            "Resource": "*",
            "Principal": "*"
        }
    ]
}
"""


# https://github.com/duo-labs/parliament/blob/main/parliament/community_auditors/privilege_escalation.py -> 1,2,3
# TODO: some way to represent combinations of permissions
DIRECT_PRIVESC_PERMISSIONS = [
    "iam:PassRole",
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "iam:UpdateLoginProfile",
    "iam:CreatePolicyVersion",
    "iam:SetDefaultPolicyVersion",
    "iam:AttachUserPolicy",
    "iam:AttachGroupPolicy",
    "iam:AttachRolePolicy",
    "iam:PutUserPolicy",
    "iam:PutGroupPolicy",
    "iam:PutRolePolicy",
    "iam:AddUserToGroup",
    "iam:UpdateAssumeRolePolicy",
]

# https://kmcquade.com/sensitive-aws-api-calls/
CREDENTIAL_ACCESS_PERMISSIONS = [
    "chime:CreateApiKey",
    "codepipeline:PollForJobs",
    "cognito-identity:GetOpenIdToken",
    "cognito-identity:GetOpenIdTokenForDeveloperIdentity",
    "cognito-identity:GetCredentialsForIdentity",
    "connect:GetFederationToken",
    "connect:GetFederationTokens",
    "ecr:GetAuthorizationToken",
    "gamelift:RequestUploadCredentials",
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "iam:CreateServiceSpecificCredential",
    "iam:ResetServiceSpecificCredential",
    "iam:UpdateAccessKey",
    "lightsail:GetInstanceAccessDetails",
    "lightsail:GetRelationalDatabaseMasterUserPassword",
    "rds-db:connect",
    "redshift:GetClusterCredentials",
    "sso:GetRoleCredentials",
    "mediapackage:RotateChannelCredentials",
    "mediapackage:RotateIngestEndpointCredentials",
    "sts:AssumeRole",
    "sts:AssumeRoleWithSaml",
    "sts:AssumeRoleWithWebIdentity",
    "sts:GetFederationToken",
    "sts:GetSessionToken",
    # https://github.com/duo-labs/parliament/blob/main/parliament/community_auditors/credentials_exposure.py
    # has these additional permissions as compared to the original list
    "cognito-idp:AssociateSoftwareToken",
    "iot:AssumeRoleWithCertificate",
    "cognito-idp:DescribeUserPoolClient",
]

EC2_ACCESS_PERMISSIONS = [
    "ssm:SendCommand",
    "ssm:StartSession",
    "ec2-instance-connect:SendSSHPublicKey",
    "ec2-instance-connect:SendSerialConsoleSSHPublicKey",
]


def get_allowed_actions_from_policy(policy: dict) -> Set[str]:
    """
    Get all allowed actions for a given policy and expand wildcards
    """

    all_actions = set(
        [
            f"{service}:{action}"
            for service in Settings.iam_data.services.get_service_keys()
            for action in Settings.iam_data.actions.get_actions_for_service(service)
        ]
    )

    allowed_actions = set()
    denied_actions = set()

    statements = policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    for statement in statements:  # type: dict
        if not (statement_actions := statement.get("Action")):
            statement_actions = statement.get("NotAction")
            not_action = True
        else:
            not_action = False

        effect_allow = True if statement.get("Effect") == "Allow" else False

        if isinstance(statement_actions, str):  # action: "*"
            statement_actions = [statement_actions]

        for statement_action in statement_actions:
            if statement_action.startswith("*"):
                # allow notaction * = <no op>
                # allow action    * = add *
                # deny  notaction * = <no op>
                # deny  action    * = remove *
                #
                # notaction = no op -> ignore
                if not not_action:
                    if effect_allow:  # allow *
                        allowed_actions.update(all_actions)
                    else:  # deny *
                        denied_actions.update(all_actions)

            else:
                service, action = statement_action.split(":")
                # TODO: these services are not in the IAM data or under an unxepected name (example: "macie")
                if not Settings.iam_data.services.service_exists(service):
                    logger.warn(f'Service "{service}" does not exist')
                    continue
                if "*" in action:  # wildcard in action name; ex: Get*, Create*A*, Li*
                    service_actions = Settings.iam_data.actions.get_actions_for_service(service)
                    actions = [
                        f"{service}:{service_action}"
                        for service_action in service_actions
                        if fnmatch.fnmatch(service_action, action)
                    ]
                else:
                    actions = [statement_action]

                # allow notaction iam:CreateUser = add inverse(iam:CreateUser)
                # allow action    iam:CreateUser = add iam:CreateUser
                # deny  notaction iam:CreateUser = remove inverse(iam:CreateUser)
                # deny  action    iam:CreateUser = remove iam:CreateUser
                if effect_allow:
                    if not_action:
                        denied_actions.update(actions)
                        allowed_actions.update(all_actions.difference(actions))
                    else:
                        allowed_actions.update(actions)
                else:
                    if not_action:
                        denied_actions.update(all_actions.difference(actions))
                    else:
                        denied_actions.update(actions)

    final_actions = allowed_actions.difference(denied_actions)
    return final_actions


def get_allowed_services_from_policy(policy: dict) -> Set[str]:
    """
    Get all allowed services for a given policy
    """

    allowed_actions = get_allowed_actions_from_policy(policy)
    services = [action.split(":")[0] for action in allowed_actions]
    return set(services)
