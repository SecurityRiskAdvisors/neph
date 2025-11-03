from abc import abstractmethod, ABC
from typing import List
from pathlib import Path

from .enrich import enrich_node, bulk_enrich
from .edges import populate_base_relationships
from .leads import generate_leads
from .nodes import (
    nodes,
    get_node_by_table_name,
    BaseGraphNodeT,
    GraphNodeStubT,
    GraphNodeStub,
    BaseGraphNode,
)
from .settings import Settings
from .jsonl import ingest_from_manifest_file, ingest_jsonl_rows, load_lines_from_str
from .exceptions import NodeTableNotFound, LoggedException, NodeNotFound
from .log import logger

from .aws.nodes.core import create_fixture_nodes


class BaseNodeWorkflow(ABC):
    """
    Analysis workflow for a given node or stub.
    General procedure is:
    - Run node enrichment on stub or all nodes of the provided type
    - Generate relationships corresponding to the node type
    - Generate leads corresponding to the node type
    """

    @classmethod
    def analyze(cls, node: BaseGraphNodeT | GraphNodeStubT, relationship_kwargs=None, lead_kwargs=None):
        """
        Main function used to run the workflow
        """
        relationship_kwargs = {} if not relationship_kwargs else relationship_kwargs
        lead_kwargs = {} if not lead_kwargs else lead_kwargs

        if isinstance(node, GraphNodeStub):
            node_types = [node.get_parent()]
            enrich_node(node)
        elif issubclass(node, BaseGraphNode):
            # list of node *types*
            node_types = [node]
            bulk_enrich(node)
        else:
            raise LoggedException(f'Cannot analyze unknown node type "{node}"')

        # excludes association relationships due to their dependence on the
        # mapping table. can revisit once associate table collection is reworked
        populate_base_relationships(node_types=node_types, exclude_assoc=True)
        generate_leads(node_types=node_types)


def analyze_node_or_stub(node: BaseGraphNodeT | GraphNodeStubT):
    """
    Main entrypoint for analyzing a node/stub
    """

    # eventually will implement other workflows and have some
    # mechanism to decide on the workflow to run
    BaseNodeWorkflow.analyze(node)


class BaseDataLoader(ABC):
    """
    Base data loading workflow
    """

    @classmethod
    @abstractmethod
    def load(cls, *args, **kwargs):
        pass


class BulkSqlDataLoader(BaseDataLoader):
    """
    Bulk SQL-based data loader workflow. Will upsert the node type(s) via
    SQL then trigger the analysis workflow.
    """

    @classmethod
    def load(cls, create_fixtures: bool = True, node_types: List[BaseGraphNodeT] = None):
        """
        Main function used to load data
        """

        if create_fixtures:
            create_fixture_nodes()

        if not node_types:
            node_types = []

        analyze_nodes = []

        for node in nodes():
            # if a list of tables is provided and the node
            # table is not in that list, skip it
            if len(node_types) > 0 and node not in node_types:
                continue

            # otherwise insert + analyze
            try:
                node.upsert_bulk_from_sql()
            except Exception as e:
                logger.warn(f'Error ingesting "{node.__name__}" ({e})')

            analyze_nodes.append(node)

        # this does the same as the CDC, so no need to run
        if not Settings.use_cdc:
            for node in analyze_nodes:
                analyze_node_or_stub(node)


class JsonlDataLoader(BaseDataLoader):
    """
    JSONL-based data loader workflow. Will upsert the node type(s) via
    provided JSON data then trigger the analysis workflow.
    """

    @classmethod
    def load(cls, manifest_path: str | Path = None, table_name: str = None, jsonl_path: str | Path = None):
        """
        Main function used to load data
        """

        analyze_tables = []
        analyze_nodes = []

        # standard manifest ingestion
        if manifest_path:
            tables = ingest_from_manifest_file(manifest_path)
            analyze_tables.extend(tables)

        # direct jsonl file ingestion
        elif jsonl_path and table_name:
            if isinstance(jsonl_path, str):
                jsonl_path = Path(jsonl_path)

            if jsonl_path.stat().st_size != 0:
                rows = load_lines_from_str(jsonl_path.read_text())
                ingest_jsonl_rows(table_name, rows)
                analyze_tables.append(table_name)

        # only submit nodes to analysis
        for table in analyze_tables:
            try:
                node_cls = get_node_by_table_name(table)
            except (NodeTableNotFound, NodeNotFound):
                pass
            else:
                analyze_nodes.append(node_cls)

        # this does the same as the CDC, so no need to run
        if not Settings.use_cdc:
            for node in analyze_nodes:
                analyze_node_or_stub(node)
