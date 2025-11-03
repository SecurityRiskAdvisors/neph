from abc import ABC
from typing import List, TypeVar, Optional, Type
from neo4j import Session
import csv
from io import StringIO

from .db import add_session
from .nodes import BaseGraphNodeT, BaseGraphNode, record_to_stub
from .utils import get_subclasses


type UnlabelledResult = List[dict]
"""List of report row dicts based on columnar results"""
type PropertiesTableResult = List[dict]
"""List of report row dicts based on graph nodes"""


@add_session()
def unlabelled_report(query: str, properties: List[str], session: Session = None) -> UnlabelledResult:
    """
    Run the query then return a list of results where each result is a dict
    containing only the properties from the provided properties list.

    Unlabelled reports are meant for use in cases where the Cypher
    query for a report class does not return a node but instead
    returns columns like "RETURN n.property1, n.property2"
    """
    records = session.run(query)
    results = []
    for record in records:
        result = dict()
        record_data = record.data()
        for property in properties:
            result[property] = record_data.get(property, None)
        results.append(result)
    return results


@add_session()
def property_table_report(
    node: BaseGraphNodeT, query: str, properties: List[str], session: Session = None
) -> PropertiesTableResult:
    """
    Run the query then return a list of results where each result is a dict
    containing only the properties from the provided properties list.

    Property reports are meant for use in cases where the Cypher
    query for a report class returns a node, like "RETURN n"
    """
    records = session.run(query)
    results = []
    for record in records:
        stub = record_to_stub(record[0])
        property_values = {prop: getattr(stub, prop, "") for prop in properties} if properties else dict()
        # add the node id to the exported properties
        if node.id not in property_values:
            property_values[node.id] = getattr(stub, node.id)
        # add the account id to the exported properties
        if "account_id" not in property_values:
            property_values["account_id"] = getattr(stub, "account_id")
        results.append(property_values)

    return results


class PropertiesTable(ABC):
    """
    Base property table class

    Class used for generating reports based on a list of properties for a node.
    For example, you can use this to implement static configuration checks for a given
    node type by overriding the query method in a child class to filter nodes
    using a desired criteria.

    Base report method expects the query will return a record with a label tied to
    a graph node class. If this is node the case, use the unlabelled_report method to
    generate a report.

    Child classes should typically include the account_id property in the property list as well as the node ID property.
    """

    node: BaseGraphNodeT
    properties: Optional[List[str]] = ["account_id"]

    @classmethod
    def query(cls, *args, **kwargs):
        querystr = f"""
        MATCH (n:{cls.node.label})
        RETURN n
        """
        return querystr

    @classmethod
    @add_session()
    def report(cls, session: Session = None, *query_args, **query_kwargs) -> PropertiesTableResult | UnlabelledResult:
        """
        Main function used to generate the report
        """
        return property_table_report(
            node=cls.node, query=cls.query(*query_args, **query_kwargs), properties=cls.properties
        )


PropertiesTableT = TypeVar("PropertiesTableT", bound=Type[PropertiesTable])


def property_table_as_csv(table: PropertiesTableT) -> str:
    """
    Generate a CSV from the property table class
    """
    results = table.report()
    str_f = StringIO()
    fieldnames = [*table.properties]
    if table.node != BaseGraphNode:
        fieldnames.append(table.node.id)
    csv_writer = csv.DictWriter(str_f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    csv_writer.writeheader()
    for result in results:
        csv_writer.writerow(result)
    csv_content = str_f.getvalue()
    str_f.close()
    return csv_content


def reports() -> List[PropertiesTableT]:
    return list(get_subclasses(PropertiesTable))
