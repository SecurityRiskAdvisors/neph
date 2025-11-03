import requests
import json
from typing import List, Optional, Tuple, Set
from neo4j import Session
from dataclasses import dataclass, field, asdict
import re
import copy

from .collect import (
    get_permission_boundary_policies_for_stub,
    get_identity_policies_for_stub,
    get_resource_policy_for_resource,
    get_scps_for_account,
    get_rcps_for_account,
    get_org_id_for_account,
    get_transitive_roles_for_arn,
)
from .exceptions import NodeNotFound, LoggedException, SimulationRequestError
from .settings import Settings
from .nodes import get_stub_by_arn
from .utils import ARN, deep_get
from .db import add_session
from .log import logger

from .aws.policies import ALLOW_ALL_SCP, ActionString
from .aws.nodes.core import Service
from .aws.equivalence import get_equivalent_actions
from .aws.resources import get_details_for_action
from .aws.principals import format_principal_str_or_arn


type ConditionsDict = dict[str, List[str]]
"""A dict of simulation context key-values like { <key> : [ <value> ] }"""
type SimulationResult = bool
"""If a simulation passed/failed"""
type SimulationResultsDict = dict
"""Simulation result full analysis dict"""
# see https://github.com/cloud-copilot/iam-simulate/blob/main/src/simulation_engine/simulationEngine.ts -> SimulationResult
type SimulationOutcome = Tuple[SimulationResult, SimulationResultsDict]
"""Combination type of the simulation pass/fail and analysis details"""
type SimulationReqResp = Tuple[Simulation, SimulationResultsDict]
"""Combination type of the simulation request and response"""
type SimulationOutcomeEx = Tuple[SimulationResult, SimulationResultsDict, List[SimulationReqResp] | None]
"""Combination type of the simulation pass/fail and analysis details. Can also include a list of additional analysis request+responses."""
type SimulationResultsSummaryDict = dict[str, str]
"""Summarized simulation analysis dict containing only the analysis outcomes (e.g. identity/resource analysis pass/fail)"""
type SimulationIamPolicy = dict
"""IAM policy document JSON formatted for use in simulator"""
type RelationshipProperties = dict
"""Dict of key-values meant to be added to a Cypher relationship"""
type ArnSet = Set[str]
"""Set of ARNs (as strings)"""


@dataclass
class SimulationRequestResource:
    resource: str
    accountId: str


@dataclass
class SimulationRequest:
    principal: str
    action: ActionString
    contextVariables: dict
    resource: SimulationRequestResource


@dataclass
class Simulation:
    request: SimulationRequest
    serviceControlPolicies: List[SimulationIamPolicy] = field(default_factory=list)
    resourceControlPolicies: List[SimulationIamPolicy] = field(default_factory=list)
    identityPolicies: List[SimulationIamPolicy] = field(default_factory=list)
    permissionBoundaryPolicies: List[SimulationIamPolicy] = field(default_factory=list)
    resourcePolicy: Optional[SimulationIamPolicy] = field(default=None)


def get_possible_conditions(result: str, analysis: dict) -> ConditionsDict:
    """
    Generate a list of possible condition key-values to add to the simulation
    request context based on the analysis details.
    """
    possible_context_additions = dict()
    analyze_conditions = False
    # TODO: multiple differing matches?
    if result == "ImplicitlyDenied":
        """
        example with value dict:

        "conditions": [
          {
            "operator": "ArnEquals",
            "conditionKeyValue": "iam:PermissionsBoundary",
            "values": {
              "value": "arn:aws:iam::*:policy/boundary",
              "matches": false
            },
            "matches": false,
            "failedBecauseMissing": true
          }
        ]

        example with value list:

        "conditions": [
          {
           "operator": "ArnEquals",
           "conditionKeyValue": "iam:PermissionsBoundary",
           "values": [
             {
               "value": "arn:aws:iam::*:policy/boundary1",
               "matches": false
             {,
             {
               "value": "arn:aws:iam::*:policy/boundary2",
               "matches": false
             }
           ],
           "matches": false,
           "failedBecauseMissing": true
          }
        ]
        """
        statement_type = "unmatchedStatements"
        condition_type = "failedBecauseMissing"
        analyze_conditions = True
    elif result == "ExplicitlyDenied":
        # if the condition is on a deny statement, it works differently
        """
        example (can be list or dict like above):

        "conditions": [
          {
            "operator": "BoolIfExists",
            "conditionKeyValue": "aws:SecureTransport",
            "values": {
              "value": "false",
              "matches": true
            },
            "matches": true,
            "matchedBecauseMissing": true
          }
        ]
        """
        statement_type = "denyStatements"
        condition_type = "matchedBecauseMissing"
        analyze_conditions = True

    if analyze_conditions:
        # return format is a dict of condition keys -> list of possible values
        for statement in analysis.get(statement_type, []):  # type: dict
            for condition in statement.get("explain", {}).get("conditions", []):
                if condition.get(condition_type, False):
                    condition_key = condition.get("conditionKeyValue")

                    if condition_key == "aws:principalArn":
                        continue

                    condition_values = condition.get("values")
                    if isinstance(condition_values, dict):
                        condition_values_list = [condition_values]
                    elif isinstance(condition_values, list):
                        condition_values_list = condition_values
                    else:
                        raise LoggedException(
                            f"Unknown condition value format in simulation result (Result data: {json.dumps(analysis)})"
                        )

                    for condition_value in condition_values_list:
                        if condition_value.get("matches", None) is not None:  # could be a boolean
                            possible_context_additions.setdefault(condition_key, []).append(
                                condition_value.get("value")
                            )
    return possible_context_additions


def suggest_condition(simulation_result: dict) -> ConditionsDict | None:
    """
    Generate a merged request context by looking at the identity and resource
    simulation results for possible condition issues.
    """

    # TODO: cleanup

    identity_analysis: dict = simulation_result.get("identityAnalysis", {})
    identity_result = identity_analysis.get("result")
    identity_additions = get_possible_conditions(identity_result, identity_analysis)

    resource_analysis: dict = simulation_result.get("resourceAnalysis", {})
    resource_result = resource_analysis.get("result")
    resouce_additions = get_possible_conditions(resource_result, resource_analysis)

    merged_additions = copy.copy(identity_additions)
    for condition, values in resouce_additions.items():
        if condition in merged_additions:
            for value in values:
                if value not in merged_additions[condition]:
                    merged_additions[condition].append(value)
        else:
            merged_additions[condition] = values

    # the scp analysis has a different structure than the others
    # it has a top-level result + an ouAnaylsis sub-section that is
    # a list of analyses
    scp_analysis: dict = simulation_result.get("scpAnalysis", {}).get("ouAnalysis", {})
    for ou_analysis in scp_analysis:
        ou_result = ou_analysis.get("result")
        ou_additions = get_possible_conditions(ou_result, ou_analysis)
        for condition, values in ou_additions.items():
            if condition in merged_additions:
                for value in values:
                    if value not in merged_additions[condition]:
                        merged_additions[condition].append(value)
            else:
                merged_additions[condition] = values

    if merged_additions == dict():
        return None
    return merged_additions


def fixup_sim_request_resource(simulation: Simulation):
    """
    If a simulation's target resource is a blanket wildcard ("*"), convert it to
    an appropriate ARN wildcard ("arn:aws:<service>:*:*:<resource>/*")
    for the simulation action.
    """

    # this section resolves blanket resource wildcards to resource ARN wildcards
    # ex:       { action: "ssm:GetParameter", resource: "*" }
    # becomes   { action: "ssm:GetParameter", resource: "arn:aws:ssm:*:*:parameter/*" }
    if simulation.request.resource.resource == "*":
        arns = []
        # a method might have >1 resource type tied to it, so there could be multiple wildcard ARN matches
        # TODO: some way to determine the best match
        for resource, details in get_details_for_action(simulation.request.action):
            if arn := details.get("arn", None):
                wildcard_arn = re.sub("\\${.*?}", "*", arn)
                arns.append(wildcard_arn)

        arn_len = len(arns)
        if arn_len == 1:
            simulation.request.resource.resource = arns[0]
        elif arn_len == 0:
            logger.warn("Cannot resolve wildcard to resource ARN wildcard")
        elif arn_len > 1:
            logger.warn(
                "Resolved wildcard to multiple resource ARN wildcards. Selecting first match but this may cause unintended behavior"
            )
            simulation.request.resource.resource = arns[0]


def send_simulation_request(simulation: Simulation) -> SimulationOutcome:
    """
    Serialize the simulation request then submit it to the simulator API
    """
    simulation_dict = asdict(simulation)
    response = requests.post(f"{Settings.simulator_url}", json=simulation_dict, timeout=3)
    if response.status_code == 200:
        outcome_dict = response.json()

        match outcome_dict.get("result"):
            # TODO: check other variations of outcomes + also modify to be a wildcard match like Allowed*
            case "Allowed" | "AllowedForAccount":
                outcome = True
            case "ExplicitlyDenied" | "ImplicitlyDenied":
                outcome = False
            case _:
                # TODO: undefined
                raise LoggedException("Error running simulation")

        return outcome, outcome_dict

    else:
        raise SimulationRequestError("Error connecting to simulator")


def simulate_equivalent_actions(
    simulation: Simulation, service_principal: bool = False
) -> Tuple[SimulationResult, List[SimulationReqResp]] | None:
    """
    Re-run a simulation for each equivalent action (see aws/equivalence.py)
    """

    # TODO: how to handle different resource types for equiv actions?

    if equivalent_actions := get_equivalent_actions(simulation.request.action):
        alternative_results = []
        alternative_outcomes = []

        for action in equivalent_actions:
            new_simulation = copy.deepcopy(simulation)
            new_simulation.request.action = action

            # change the requested action to an equivalent then re-run simulation
            simulation_outcome, simulation_results, _ = run_simulation(
                simulation=new_simulation,
                fixup_resource=False,
                check_conditions=True,
                # TODO: could possibly have nested equivalence?
                check_equivalence=False,
                service_principal=service_principal,
            )
            logger.debug(
                f'Re-ran simulation for "{simulation.request.action}" (principal="{simulation.request.principal}") using equivalent action "{action}" (outcome={simulation_outcome})'
            )

            # store a summary of the new simulation as a dict of
            # the action and the summarized view
            # ex: ec2:CreateInstance: { "result": True, "identity": ... }
            alternative_results.append((new_simulation, simulation_results))
            alternative_outcomes.append(simulation_outcome)

        # if any of the equivalent actions were allowed, override
        # the original outcome then store the equivalent simulation summaries
        # on the relationship
        new_outcome = any(alternative_outcomes)

        if new_outcome:
            return new_outcome, alternative_results

    # if no equivalent actions, return nothing
    return None


def simulate_with_conditions(
    simulation: Simulation, conditions: dict, service_principal: bool = False
) -> Tuple[SimulationResult, List[SimulationReqResp]] | None:
    """
    Re-run a simulation using the new context
    """

    new_context = {}
    for k, v in conditions.items():
        value_len = len(v)
        # TODO: some way to determine the best match
        if value_len == 0:
            continue
        elif value_len > 1:
            logger.warn(
                f'Resolved condition value for key "{k}" to multiple possible values. Selecting first match but this may cause unintended behavior'
            )
        condition_value = v[0]
        new_context[k] = condition_value

    new_simulation = copy.deepcopy(simulation)
    new_simulation.request.contextVariables = {**simulation.request.contextVariables, **new_context}
    outcome, outcome_results, _ = run_simulation(
        simulation=new_simulation,
        fixup_resource=False,
        check_conditions=False,
        check_equivalence=False,
        service_principal=service_principal,
    )
    logger.debug(
        f'Re-ran simulation for "{simulation.request.action}" (principal="{simulation.request.principal}") with additional context "{json.dumps(new_context)}" (outcome={outcome})'
    )
    if outcome:
        return outcome, [(new_simulation, outcome_results)]
    return None


def run_simulation(
    simulation: Simulation,
    fixup_resource: bool = True,
    check_conditions: bool = True,
    check_equivalence: bool = True,
    service_principal: bool = False,
) -> SimulationOutcomeEx:
    """
    Run a simulation as-is. If it fails, retry by updating it based on API
    equivalence and conditions context updates.
    """

    if fixup_resource:
        fixup_sim_request_resource(simulation)

    # TODO: more generally handle retries and recursion
    #       likely need some type of matrix for
    #       equivalence, context changes, etc
    # TODO: should also make it clear which sub-simulations
    #       caused a change in the top-level outcome
    #       e.g. passing sub-sims vs failed sub-sims
    #       or possibly on include passing ones

    outcome, outcome_results = send_simulation_request(simulation)
    # if service_principal:
    #     outcome, _ = analyze_sim_results_for_service(outcome_results)

    additional_outcomes = None
    logger.debug(
        f'Ran simulation for "{simulation.request.action}" (principal="{simulation.request.principal}") (outcome={outcome})'
    )

    if not outcome:
        """
        If not allowed, retry several times by modifying the simulation.
        First check if the failure was due to a conditions error
            -> If so, re-run by populating missing condition keys
        Then check if the an equivalent action is allowed
            -> Also try condition checks on those actions as well
        Final simulation outcome is a pass if any sub-simulation is a pass
        """

        additional_outcomes = []
        if check_conditions:
            if condition_suggestions := suggest_condition(outcome_results):
                if new := simulate_with_conditions(
                    simulation=simulation, conditions=condition_suggestions, service_principal=service_principal
                ):
                    new_outcome, new_results = new
                    if new_outcome:
                        outcome = new_outcome
                        additional_outcomes.extend(new_results)

        if check_equivalence:
            if new := simulate_equivalent_actions(simulation=simulation, service_principal=service_principal):
                new_outcome, new_results = new
                if new_outcome:
                    outcome = new_outcome
                    additional_outcomes.extend(new_results)

    # either none or non-empty list
    if additional_outcomes and len(additional_outcomes) == 0:
        additional_outcomes = None

    return outcome, outcome_results, additional_outcomes


def fmt_policy_for_sim(policy: dict | str) -> SimulationIamPolicy:
    """
    Format a policy document JSON for use in a simulation.
    Simulation policies require specific keys not present in
    normal policy documents.
    """

    if isinstance(policy, str):
        policy = json.loads(policy)
    # the simulation requires these key names for policy docs
    if "PolicyDocument" in policy:
        policy["policy"] = policy["PolicyDocument"]
        del policy["PolicyDocument"]

        if "PolicyName" in policy:
            policy["name"] = policy["PolicyName"]
            del policy["PolicyName"]

    elif "Statement" in policy:
        policy = {"policy": policy, "name": "name"}

    return policy


def fmt_organization_policies_for_sim(policies: List[SimulationIamPolicy], org_id: str):
    return [{"orgIdentifier": org_id, "policies": policies}]


def summarize_sim_results(results_dict: dict) -> SimulationResultsSummaryDict:
    """
    Generate a dict of the top-level outcomes for each analysis type in a simulation result
    """

    summary = {
        "result": results_dict.get("result"),
        # sometimes these are not present
        # for example: permissionBoundaryAnalysis may not be present for
        #              service principal simulations
        "identity": deep_get(results_dict, ["identityAnalysis", "result"]),
        "resource": deep_get(results_dict, ["resourceAnalysis", "result"]),
        "rcp": deep_get(results_dict, ["rcpAnalysis", "result"]),
        "scp": deep_get(results_dict, ["scpAnalysis", "result"]),
        "boundary": deep_get(results_dict, ["permissionBoundaryAnalysis", "result"]),
    }
    return summary


def analyze_sim_results_for_service(results_dict: dict) -> Tuple[SimulationResult, RelationshipProperties]:
    """
    Analyze the results of a simulation where the principal was service principal.
    Service principals do not have identity policies, so that will always fail
    in the analysis, causing the final verdict to be a fail. This function
    performs a second pass of the results and ignores the identity and permission
    boundary analysis.
    """

    """
    # originally, the simulator did not handle service principals 
    # this code was added (prior to conditions suggestions) to handle
    # service principal outcomes by only checking some of the analysis
    # and ignoring the rest
    # 
    # the simulator added service principal support in 
    # https://github.com/cloud-copilot/iam-simulate/commit/02164b988a68070da7d4006de8e7c3e8a5977446
    #
    # leaving this block here for future reference
    additional_rel_properties = {}
    rcp_allowed = results_dict.get("rcpAnalysis").get("result") == "Allowed"
    scp_allowed = results_dict.get("scpAnalysis").get("result") == "Allowed"
    resource_allowed = results_dict.get("resourceAnalysis").get("result") in ["Allowed", "NotApplicable"]
    if not resource_allowed:
        for statement in results_dict.get("resourceAnalysis").get("unmatchedStatements"):
            if (
                statement.get("actionMatch") == True
                and statement.get("principalMatch") == "Match"
                and statement.get("resourceMatch") == True
                and statement.get("conditionMatch") in [False, "NoMatch"]
            ):
                # TODO: tie into conditions suggestions
                resource_allowed = True
                additional_rel_properties["conditions"] = json.dumps(statement.get("conditions"))

    outcome = all([rcp_allowed, scp_allowed, resource_allowed])

    return outcome, additional_rel_properties
    """

    logger.warning("analyze_sim_results_for_service deprecated and no longer required")
    return results_dict.get("result"), {}


def run_simulation_and_generate_relationship(
    simulation: Simulation, service_principal: bool = False
) -> Tuple[SimulationResult, str | None]:
    """
    Given a simulation, run it and generate a relationship
    with the appropriate properties.
    Also implements logic for handling service principal simulations.
    Generated relationship will contain raw and summarized results
    for the original simulation as well as summarized results for
    equivalence simulations.
    Top-level result is the original outcome, but if any sub-simulation
    is passes, the top-level outcome will reflect that. Successful sub-simulation
    results and summaries are also stored on the relationship.
    """
    simulation_outcome, simulation_results, additional_results = run_simulation(
        simulation=simulation, service_principal=service_principal
    )
    results_summary = summarize_sim_results(simulation_results)

    # filter out unsuccessful sub-simulations
    # then prepare a list to include in the relationship
    additionals = []
    if additional_results and len(additional_results) > 0:
        for additional_result in additional_results:
            if additional_result[1].get("result") == "Allowed":
                additional_summary = summarize_sim_results(additional_result[1])
                additionals.append(
                    {
                        "request": asdict(additional_result[0]),
                        "response": additional_result[1],
                        "summary": additional_summary,
                    }
                )

    if not simulation_outcome:
        return False, None
    else:
        key, method = simulation.request.action.split(":")
        # replace service:action separator with underscore
        # remove "-"s (e.g. in service names)
        relation_label = simulation.request.action.replace(":", "_").replace("-", "").upper()
        relation_properties = {
            "action": simulation.request.action,
            "key": key,
            "method": method,
            "resource": str(simulation.request.resource.resource),
            "simulation": json.dumps(asdict(simulation)),
            "result": json.dumps(simulation_results),
            "summary": json.dumps(results_summary),
            "additional_results": json.dumps(additionals),
        }

        relation_properties_str_parts = []
        for k, v in relation_properties.items():
            key = k
            value = v.replace("'", r"\'")
            merged = f"{key}: '{value}'"
            relation_properties_str_parts.append(merged)
        relation_properties_str = ", ".join(relation_properties_str_parts)

        relation_str = f""":{relation_label}{{ {relation_properties_str} }}"""

        return True, relation_str


# TODO: how best to handle actions not affected by SCPs?
#       see: https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html#not-restricted-by-scp
#       notably: service-linked roles + principals in the management & deleg admin account


@add_session()
def service_can_perform(
    principal: str,  # unregionalized
    action: ActionString,
    resource: str,  # arn
    resource_account: str = None,
    context: dict = None,
    include_org_policies: bool = False,
    write_to_graph: bool = True,
    session: Session = None,
) -> SimulationResult:
    """
    Works similar to iam_principal_can_perform but used to check if an AWS service can perform an action.
    Specifically Services themselves, not service/service-linked roles.
    e.g. if you give CloudTrail write access to a bucket via a bucket policy, you would use this function to validate that policy.

    This works differently from normal principals in the following ways:
     - can skip identity policy collection since services have no identity policies
     - node lookup will need to use the Service node type (created via fixtures creation)
    """

    service = principal
    if not service.endswith(".amazonaws.com"):
        service = f"{principal}.amazonaws.com"

    context = context if context else {}

    # need to be more strict about the resource and its account
    # as service actions are more resource-bound than the normal sim

    if resource and resource.startswith("arn"):
        resource = ARN.from_string(resource)
    else:
        # TODO: revisit
        raise Exception("Resource must be valid ARN")

    if not resource_account:
        if resource and resource.account_id:
            resource_account = resource.account_id

    if not resource_account:
        raise LoggedException("Cannot determine resource account")

    resource_policy = get_resource_policy_for_resource(resource)

    rc_policies: List[dict] = []
    if include_org_policies:
        sc_policies = get_scps_for_account(account_id=resource_account)
        rc_policies = get_rcps_for_account(resource_account)

        sc_policies = [fmt_policy_for_sim(policy) for policy in sc_policies]
        rc_policies = [fmt_policy_for_sim(policy) for policy in rc_policies]

        org_id = get_org_id_for_account(account_id=resource_account)
        sc_policies = fmt_organization_policies_for_sim(org_id=org_id, policies=sc_policies)
        rc_policies = fmt_organization_policies_for_sim(org_id=org_id, policies=rc_policies)
    else:
        sc_policies = [json.loads(ALLOW_ALL_SCP)]

    simulation = Simulation(
        request=SimulationRequest(
            principal=service,
            action=action,
            contextVariables=context,
            resource=SimulationRequestResource(resource=str(resource), accountId=resource_account),
        ),
        serviceControlPolicies=sc_policies,
        resourceControlPolicies=rc_policies,
        identityPolicies=[],
        permissionBoundaryPolicies=[],
        resourcePolicy=resource_policy,
    )

    simulation_result, relation_str = run_simulation_and_generate_relationship(
        simulation=simulation, service_principal=True
    )
    if simulation_result and write_to_graph:
        service_key = service.split(".")[0]
        target_service_key = action.split(":")[0]

        start_node = f"""MATCH (start:{Service.label}{{ key:"{service_key}" }})"""
        end_node = f"""MERGE (end:{Service.label}{{ key:"{target_service_key}" }})"""

        query = f"""{start_node}
        {end_node}
        MERGE (start)-[{relation_str}]->(end)"""
        session.run(query)

    return simulation_result


def generate_sim_for_iam_principal(
    principal: str | ARN,
    action: ActionString,
    resource: str = None,
    resource_account: str = None,
    context: dict = None,
    include_org_policies: bool = False,
) -> Simulation:
    """
    Generate a simulation request for a given principal.
    """

    principal, original_principal = format_principal_str_or_arn(principal)

    try:
        node = get_stub_by_arn(arn=principal)
    except NodeNotFound as e:
        raise e

    # principal attached and inline policies and group attached and inline policies
    identity_policies = get_identity_policies_for_stub(node, include_groups=True)

    # principal permission boundaries
    boundary_policies = get_permission_boundary_policies_for_stub(node)

    # resource policies
    resource_arn = None
    resource_policy = None
    if resource and resource.startswith("arn"):
        resource_arn = ARN.from_string(resource)
        resource_policy = get_resource_policy_for_resource(resource_arn)

    # if the resource account isnt explicitly provided
    if not resource_account:
        # first try getting it from the resource arn
        if resource_arn and resource_arn.account_id:
            resource_account = resource_arn.account_id
        # then just fall back to the caller arn
        else:
            resource_account = node.account_id

    context = context if context else {}

    # TODO: EC2 instance roles?
    #       ultimately these are just normal roles, it may end up being a matter of just mapping
    #       the trust policy piece to EC2

    rc_policies: List[dict] = []
    # this is different from Settings.load_aws_org as that deals with data loading into the graph
    # whereas this deals with using data already in the graph
    if include_org_policies:
        sc_policies = get_scps_for_account(account_id=node.account_id)
        if resource_arn:  # only pull RCPs if theres a resource
            # https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_rcps.html#rcp-effects-on-permissions
            # RCPs are based on the resource's account
            rc_policies = get_rcps_for_account(resource_account)

        sc_policies = [fmt_policy_for_sim(policy) for policy in sc_policies]
        rc_policies = [fmt_policy_for_sim(policy) for policy in rc_policies]

        org_id = get_org_id_for_account(account_id=node.account_id)
        sc_policies = fmt_organization_policies_for_sim(org_id=org_id, policies=sc_policies)
        rc_policies = fmt_organization_policies_for_sim(org_id=org_id, policies=rc_policies)
    else:
        sc_policies = [json.loads(ALLOW_ALL_SCP)]

    identity_policies = [fmt_policy_for_sim(policy) for policy in identity_policies]
    boundary_policies = [fmt_policy_for_sim(policy) for policy in boundary_policies]

    # misc notes:
    # - iam-simulate will validate the provided resource against
    #   the resource type arn via a regex match
    #   which means you need to use a wildcard instead of blank
    #   e.g. for an account in the ARN, use '*' not *null*
    #   https://github.com/cloud-copilot/iam-simulate/blob/main/src/util.ts#L303 (getResourceTypesForAction)

    simulation = Simulation(
        request=SimulationRequest(
            principal=node.arn if not original_principal else str(original_principal),
            action=action,
            contextVariables=context,
            resource=SimulationRequestResource(resource=resource, accountId=resource_account),
        ),
        serviceControlPolicies=sc_policies,
        resourceControlPolicies=rc_policies,
        identityPolicies=identity_policies,
        permissionBoundaryPolicies=boundary_policies,
        resourcePolicy=resource_policy,
    )

    return simulation


# TODO: instead of using a principal, switch to new NodeFinder syntax
@add_session()
def iam_principal_can_perform(
    principal: str | ARN,
    action: ActionString,
    resource: str = None,
    resource_account: str = None,
    context: dict = None,
    include_org_policies: bool = False,
    write_to_graph: bool = True,
    check_transitivity: bool = False,
    session: Session = None,
) -> Tuple[SimulationResult, ArnSet | None]:
    """
    Check if a given principal can perform the given action against the resource.
    The simulation request is populated by doing the following:
    - Resolve the principal to a node
    - Get all identity policies for the node
    - Get all group identity policies for groups the node is a member of
    - Get permission boundaries for the node
    - Get the resource policy for the target resource
    - Get all organization SCPs and RCPs

    If the simulation is successful, setting write_to_graph to True will
    create a new relationship between the principal and the Service the resource
    is tied to. The relationship type will be a normalized version of the action.
    Simulation request and result details are included on the relationship as
    properties.
    Example:
        Principal:    arn:aws:iam::12345:user/user1
        Action:       s3:GetObject
        Resource:     arn:aws:s3:::bucket1/file1.txt
        Relationship: (:IamUser{...})-[:S3_GETOBJECT{...}]->(:Service{key:"s3"})

    """

    simulation = generate_sim_for_iam_principal(
        principal=principal,
        action=action,
        resource=resource,
        resource_account=resource_account,
        context=context,
        include_org_policies=include_org_policies,
    )
    principal_arn = simulation.request.principal

    simulation_result, relation_str = run_simulation_and_generate_relationship(
        simulation=simulation, service_principal=True
    )

    transitive_successes = set()

    if simulation_result:
        if write_to_graph:
            target_service_key = action.split(":")[0]

            start_node = f"""MATCH (start{{ arn:"{principal_arn}" }})"""

            # TODO: for non-wildcard resources, map to the target resource node
            #       will need to switch to using NodeFinder first in order to handle
            #       nodes with weird anchor properties
            #       possibly also do a query first to see if the node exists
            #           and if not fall back to the service node
            end_node = f"""MERGE (end:{Service.label}{{ key:"{target_service_key}" }})"""

            query = f"""{start_node}
            {end_node}
            MERGE (start)-[{relation_str}]->(end)"""
            session.run(query)

    else:
        if check_transitivity:
            # i dont particularly like the way the transitivity check is implemented
            # however, ill refrain from refactoring until i figure out the
            # retry matrix refactor that will be for the conditions & equivalence
            # functionality as the transitivity checks is basically the same thing
            # and would benefit from also being able to configure those for
            # transitive sims

            transitive_arns = get_transitive_roles_for_arn(arn=principal)

            for transitive_arn in transitive_arns:
                transitive_result, _ = iam_principal_can_perform(
                    principal=transitive_arn,
                    action=action,
                    resource=resource,
                    resource_account=resource_account,
                    context=context,
                    include_org_policies=include_org_policies,
                    write_to_graph=write_to_graph,
                    check_transitivity=False,
                )
                if transitive_result:
                    transitive_successes.add(transitive_arn)

    if len(transitive_successes) == 0:
        transitive_successes = None

    return simulation_result, transitive_successes
