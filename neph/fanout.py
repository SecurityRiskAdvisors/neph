from abc import ABC
from typing import TypeVar, List, Type, Tuple
from neo4j import Session

from .utils import ARN, get_subclasses
from .nodes import get_stub_by_arn, GraphNodeStubT, BaseGraphNodeT
from .sim import (
    fmt_policy_for_sim,
    generate_sim_for_iam_principal,
    run_simulation,
    SimulationResult,
)
from .collect import get_identity_policies_for_stub, get_resource_policy_for_resource
from .db import add_session

from .aws.policies import (
    get_allowed_actions_from_policy,
    get_allowed_services_from_policy,
)


class FanoutStrategy(ABC):
    """
    Base fanout class

    Fanouts are used for initial/incremental discovery activities for a given principal,
    such as looking for possible next hops.
    """

    @classmethod
    def fanout(cls, principal_stub: GraphNodeStubT):
        pass


type PermissionsFanoutResult = list
"""List of permissions returned from a permissions heuristic fanout"""


class PermissionsFanout(FanoutStrategy):
    """
    Fanout strategy based on quick checks of a principal's *identity* policies.
    Returns a list of (potentially) allowed actions.
    Should return a list of permissions.
    """

    permissions: List[str]

    @classmethod
    def fanout(cls, principal_stub: GraphNodeStubT) -> PermissionsFanoutResult:
        permissions = set(cls.permissions)

        shared_permissions = set()
        for identity_policy in get_identity_policies_for_stub(stub=principal_stub, include_groups=True):
            policy_json = fmt_policy_for_sim(identity_policy).get("policy")
            allowed_actions = get_allowed_actions_from_policy(policy_json)
            shared_permissions.update(allowed_actions.intersection(permissions))

        return PermissionsFanoutResult(shared_permissions)


type ServicesFanoutResult = list
"""List of services returned from a service heuristic fanout"""


class ServicesFanout(FanoutStrategy):
    """
    Fanout strategy based on quick checks of a principal's identity policies.
    Returns a list of (potentially) allowed services.
    """

    @classmethod
    def fanout(cls, principal_stub: GraphNodeStubT) -> ServicesFanoutResult:
        services = set()
        for identity_policy in get_identity_policies_for_stub(stub=principal_stub, include_groups=True):
            policy_json = fmt_policy_for_sim(identity_policy).get("policy")
            allowed_services = get_allowed_services_from_policy(policy_json)
            services.update(allowed_services)

        return ServicesFanoutResult(services)


type BruteForceFanoutResult = List[Tuple[str, SimulationResult]]
"""List of ARNs and a pass/fail on if they can perform the simulated action"""


class BruteForceFanout(FanoutStrategy):
    """
    Brute-force attempts to perform an action using the simulator.
    Assumes the same account for the source principal and the target.
    Returns a list of resources and whether or not the simulation was allowed.
    """

    resource: BaseGraphNodeT
    action: str

    @classmethod
    @add_session()
    def fanout(cls, principal_stub: GraphNodeStubT, session: Session = None) -> BruteForceFanoutResult:
        query = f"""MATCH (n:{cls.resource.label}) WHERE n.arn is not null return n.arn"""
        records = session.run(query).values()

        # [['<arn>'], ['<arn>']]
        arns = [record[0] for record in records]
        first_arn = arns[0]
        simulation = generate_sim_for_iam_principal(
            principal=principal_stub.arn, action=cls.action, include_org_policies=True, resource=first_arn
        )

        results = []
        for arn in arns:
            resource_policy = get_resource_policy_for_resource(arn)
            simulation.resourcePolicy = resource_policy
            simulation.request.resource.resource = arn
            outcome, *_ = run_simulation(simulation=simulation)
            results.append((arn, outcome))

        return results


FanoutStrategyT = TypeVar("FanoutStrategyT", bound=Type[FanoutStrategy])
PermissionFanoutT = TypeVar("PermissionFanoutT", bound=Type[PermissionsFanout])
BruteForceFanoutT = TypeVar("BruteForceFanoutT", bound=Type[BruteForceFanout])


def fanout_principal(principal_arn: str | ARN, strategy: FanoutStrategyT):
    principal_stub = get_stub_by_arn(arn=principal_arn)
    results = strategy.fanout(principal_stub)
    return results


def fanouts() -> List[FanoutStrategyT]:
    subclasses = get_subclasses(FanoutStrategy)
    subclasses.discard(BruteForceFanout)
    subclasses.discard(PermissionsFanout)

    return list(subclasses)
