from neo4j import Session
from neo4j.graph import Path
from typing import List

from .nodes import NodeFinder, record_to_stub, GraphNodeStub
from .db import add_session, CypherQuery, PartialCypherQuery

type PathComponent = tuple
"""One or more node string representations (node label + node id property and value) and/or relationship types"""


def gen_finder_match_stmt(finder: str | NodeFinder, node_name) -> PartialCypherQuery:
    """
    Generate a Cypher MATCH statement for the given node finding specification
    """

    if isinstance(finder, str):
        finder = NodeFinder.from_str(finder)
    match = finder.cypher(node_name=node_name)
    return match


@add_session()
def add_l2r_path(start: str | NodeFinder, end: str | NodeFinder, relation: str, session: Session = None):
    """
    Create the given relationship between the two node finding specifications.
    Relationship will be directional from the start node to the end node (left-to-right).
    """

    start_name = "start"
    end_name = "end"

    start_match = gen_finder_match_stmt(finder=start, node_name=start_name)
    end_match = gen_finder_match_stmt(finder=end, node_name=end_name)

    query = f"""
    {start_match}
    {end_match}
    MERGE ({start_name})-[:{relation}]->({end_name})
    """
    session.run(query)


@add_session()
def get_l2r_paths(start: str | NodeFinder, end: str | NodeFinder, session: Session = None) -> List[PathComponent]:
    """
    Find all relationships between two node finding specifications.
    Relationship will be directional from the start node to the end node (left-to-right).
    """

    start_name = "start"
    end_name = "end"

    start_match = gen_finder_match_stmt(finder=start, node_name=start_name)
    end_match = gen_finder_match_stmt(finder=end, node_name=end_name)

    # query for all paths of any length between two nodes
    query = f"""
    {start_match}
    {end_match}
    MATCH p=({start_name})-[*1..]->({end_name})
    RETURN p
    """
    paths: List[List[Path]] = session.run(query).values()

    results = []
    for path in paths:
        # there could be multiple relationships b/w the start node and final end
        # node like (start)-[r1]->()-[r2]->(end)
        # so need to walk the path and grab each intermediary relationship and
        # node
        p = path[0]
        start_stub = record_to_stub(p.start_node, include_fakes=True)
        result = [start_stub]
        for relationship in p.relationships:
            result.append(relationship.type)
            # the end node of the last relationship in Path.relationships should
            # match the end node in Path.end_node
            result.append(record_to_stub(relationship.end_node, include_fakes=True))
        result = tuple(result)
        results.append(result)

    return results


@add_session()
def promote_l2r_leads(start: str | NodeFinder, end: str | NodeFinder, lead_type: str, session: Session = None):
    """
    Promote all leads of the given types between the two node finding specification.
    Relationship will be directional from the start node to the end node (left-to-right).
    Note: this uses apoc.refactor.rename.type, which destroys the original
    relationship, giving it a new element ID
    """

    start_name = "start"
    end_name = "end"

    start_match = gen_finder_match_stmt(finder=start, node_name=start_name)
    end_match = gen_finder_match_stmt(finder=end, node_name=end_name)

    # query for all paths of any length between two nodes
    query = f"""
    {start_match}
    {end_match}
    MATCH ({start_name})-[r:LEAD{{type: "{lead_type}"}}]->({end_name})
    CALL apoc.refactor.rename.type("LEAD", r.type, [r]) yield total
    return total
    """
    session.run(query)


def fmt_l2r_path_as_str(path: PathComponent) -> str:
    """
    Format a left-to-right path tuple as a string using the format
    (<node label>{<node id property>:<node id value>})-[:<relationship type>]->(<node label>{<node id property>:<node id value>})
    """

    path_str = ""
    for i, item in enumerate(path):
        # first item: (item)-
        # 2nd item  : [item]->
        # 3rd item  : (item)-
        # 4th item  : [item]->
        # last item : (item)

        # either a stub (node) or a string (relationship type)
        if isinstance(item, GraphNodeStub):
            path_str += str(item)
            if i + 1 != len(path):  # not the last item
                path_str += "-"
        else:
            path_str += f"[:{item}]->"

    return path_str
