from typing import Set

from .policies import ActionString

"""
Stores information on API equivalence mappings.
originally posted here: https://sra.io/blog/an-overview-of-deputies-in-aws/ -> API Equivalence

Essentially, some API calls result in other API calls being made implicitly.
For example, calling ec2:CreateImage implicitly calls ec2:CreateSnapshot behind the scenes.
These implicit calls are not subject to permissions checks nor are they constrained by boundary/org policy restrictions.
You can treat the implicitly called APIs as equivalent to the originating API call for the purposes of pathfinding.

The below EQUIVALENCE_MAPPING is a mapping of the implicitly called APIs (key) to the originating API(s) (value).
Calls to the simulator interface will use this mapping when analyzing if an action is allowed 
by checking the original action as well as any equivalent action.
"""

# TODO: pull in full list from notes
#       possibly expose something to end users to extend this list
EQUIVALENCE_MAPPING = {"ec2:CreateSnapshot": ["ec2:CreateImage"]}


def get_equivalent_actions(action: ActionString) -> Set[ActionString] | None:
    # example:
    # can Role X do Action Y?
    # lookup if Action Y in mapping (as a key)
    # if yes -> get equivalent action(s) (Action Z)
    # re-run simulation to see if Z is allowed
    # if yes -> Action Y is therefore transitively allowed
    if action in EQUIVALENCE_MAPPING:
        return set(EQUIVALENCE_MAPPING.get(action))
    else:
        return None
