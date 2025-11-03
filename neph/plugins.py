from importlib.metadata import entry_points
from enum import Enum

from .log import logger

# plugins need to be manually loaded before use


# each parent class type gets an entry group
# but ultimately you could change this to have a single entry group
# since all the code uses class hierarchies
# (so the plugin classes just need to be loaded to work)
# but i like concept of separating these by type for organization purposes
# may revisit this in the future
class EntryGroup(str, Enum):
    """
    Python entry group names
    """

    Node = "neph.node"
    Edge = "neph.edge"
    Enrichment = "neph.enrichment"
    Lead = "neph.lead"
    Report = "neph.report"
    Fanout = "neph.fanout"


def load_plugin_group(group: EntryGroup):
    """
    Load all plugins in the provided group
    """

    class_eps = entry_points(group=group.value)
    for class_ep in class_eps:
        class_ep.load()
        logger.info(f'Loaded plugin "{group.name}" for group "{group.value}"')


def load_all_plugins():
    """
    Load all plugins
    """

    for group in EntryGroup:  # type: EntryGroup
        load_plugin_group(group=group)
