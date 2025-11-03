from typing import List, Any, Self, Set
from dataclasses import dataclass
from importlib import import_module
import pathlib
from enum import Enum

from .settings import Settings


# https://stackoverflow.com/a/50173148
def deep_get(d: dict, keys: List) -> Any | None:
    """
    Safely get a nested value from a dict if it exists
    """

    if not keys or d is None:
        return d
    return deep_get(d.get(keys[0]), keys[1:])


# https://github.com/GeneralTesler/miscaws/blob/master/simclient/simclient/client.py
def split_arn_string(arn: str) -> list:
    """
    Split a string representation of an ARN
    """

    parts = arn.split(":")
    if len(parts) == 6:
        if "/" in parts[5]:
            resource = parts[5].split("/")
            parts[5] = resource[0].lower()
            parts.append("/".join(resource[1:]))
        # else:
        #        parts[6] = ""
    return parts


# https://github.com/GeneralTesler/miscaws/blob/master/simclient/simclient/client.py
@dataclass
class ARN:
    prefix: str = None
    partition: str = None
    service: str = None
    region: str = None
    account_id: str = None
    resource_type: str = None
    resource_id: str = None

    @classmethod
    def from_string(cls, arn: str) -> Self:
        # TODO: revisit
        return cls(*split_arn_string(arn=arn))

    def __str__(self):
        arn_str = f"{self.prefix}:{self.partition}:{self.service}:{self.region}:{self.account_id}:{self.resource_type}"
        if self.resource_id:
            arn_str += f"/{self.resource_id}"
        return arn_str

    @property
    def parent(self) -> "ARN":
        return ARN(
            prefix=self.prefix,
            partition=self.partition,
            service=self.service,
            region=self.region,
            account_id=self.account_id,
            resource_type=self.resource_type,
        )


def get_subclasses(cls) -> Set:
    """
    Get all subclasses of a given class
    """

    load_graph_classes()

    subclasses = set(cls.__subclasses__())
    for subclass in cls.__subclasses__():
        subclasses.update(get_subclasses(subclass))
    return subclasses


def match_subclass(cls, v: str):
    """
    Get a subclass of a class by its name (case-insensitive)
    """

    target = None
    subclasses = get_subclasses(cls)
    for subclass in subclasses:
        if subclass.__name__.lower() == v.lower():
            target = subclass
            break
    if not target:
        valid_subclasses = [c.__name__ for c in subclasses]
        raise Exception(f'Subclass "{v}" not valid child of {cls.__name__} (choices: {", ".join(valid_subclasses)})')

    return target


def cast_table_query(table: str) -> str:
    """
    Generate a SQL select query for a given Steampipe table where each
    column is cast to a varchar
    """

    columns: List[str] = Settings.steampipe_tables_schema.get(table, [])
    cast_columns = [f"cast({column} as varchar) as {column}" for column in columns]
    table_query = f"select {",".join(cast_columns)} from {Settings.steampipe_aggregator}.{table}"

    return table_query


def load_modules_in_directory(directory: str, package_prefix: str):
    """
    Load all Python modules from a given directory
    """

    for module_file in pathlib.Path(directory).parent.glob("*.py"):
        module_name = module_file.stem
        if (not module_name.startswith("_")) and (module_name not in globals()):
            import_module(f".{package_prefix}.{module_name}", __package__)


_graph_classes_loaded = False


def load_graph_classes():
    """
    Import node/edge subclasses.

    Since most graph functionality is based on class hierarchy, you need
    to explicitly load the classes so they populate their parent's __subclasses__
    """

    global _graph_classes_loaded
    if not _graph_classes_loaded:
        import_module(".aws.nodes", __package__)
        import_module(".aws.edges", __package__)
        import_module(".aws.other", __package__)
        _graph_classes_loaded = True


class CaseInsensitiveEnum(Enum):
    """
    Enum that allows for case-insensitive member lookup by name
    CaseInsensitiveEnum("key") -> CaseInsensitiveEnum.Key
    """

    @classmethod
    def _missing_(cls, value):
        # see: https://docs.python.org/3/library/enum.html#enum.Enum._missing_
        #   note that the lookup here is by name rather than by value
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        raise KeyError(f"{value} is not a valid enum member")
