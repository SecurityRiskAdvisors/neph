import pathlib
from pathlib import Path
import json
import yaml
from typing import List, Tuple
from enum import auto

from .log import logger
from .nodes import get_node_by_table_name, nodes, BaseGraphNodeT
from .edges import get_edges_by_table_name, AssocDataType, AssocRelationship, BaseRelationshipT
from .exceptions import NodeTableNotFound, EdgeTableNotFound, LoggedException, NodeNotFound
from .utils import get_subclasses, CaseInsensitiveEnum
from .settings import Settings

"""
JSONL file importer support for Steampipe individual table exports
    Example:
    > bin/steampipe_export_aws aws_iam_user --output jsonl
    
Make sure to configure the plugin via the appropriate env vars as it does not support using a workspace
"""

type JsonlRow = dict
"""Single JSON row dict from Steampipe's JSONL output"""
type ExportBashScript = str
"""Bash script for running Steampipe export commands"""


def load_lines_from_str(rows_str: str) -> List[JsonlRow]:
    """
    Given a string of JSON lines, split the string by line and deserialize the JSON data
    """

    rows = []
    lines = rows_str.split("\n")
    lines = [line for line in lines if line is not None and line != ""]
    for line in lines:
        try:
            row_dict = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f'Error decoding JSONL data: "{e}"')
        else:
            rows.append(row_dict)
    return rows


# as a future state, it would nice to have some type of generic jsonl router
# such that you could import jsonl data then use it for any type of graph
# feature. for example, a node enrichment based on import jsonl data
def ingest_jsonl_rows(table_name: str, rows: List[JsonlRow]):
    """
    Ingest the provided JSONL data.
    Will attempt to load each line as both a node and association relationship
    where the provided table name matches the corresponding class property.
    """

    node_err = False
    try:
        node_cls = get_node_by_table_name(table_name)
    except (NodeTableNotFound, NodeNotFound):
        node_err = True
    else:
        node_cls.upsert_bulk_from_jsonl(rows)

    edge_err = False
    try:
        all_edge_cls = get_edges_by_table_name(table_name)
    except EdgeTableNotFound:
        edge_err = True
    else:
        [edge_cls.populate(data_type=AssocDataType.Jsonl, data=rows) for edge_cls in all_edge_cls]

    # table could not be found anywhere
    if edge_err and node_err:
        logger.warn(f'Could not locate corresponding node or edge for table "{table_name}"')


# TODO: support specifying a node label instead of a table name
# TODO: manifest class
def ingest_from_manifest(manifest_dict: dict) -> List[str]:
    """
    Ingest a given JSONL manifest. Manifests are simple k-v JSON files that map
    the Steampipe table name to one or more JSONL files.

    Input manifest format:
        key = table name
        value = file or list of files in jsonl format
                file names can also be globbing patterns
                file names are relative to the controller's working directory, not the manifest file

    example manifest:
        aws_iam_user: foo/account_xyz.jsonl
        aws_iam_role:
        - account_1234.jsonl
        - account_*.jsonl
    """

    for table_name, files in manifest_dict.items():  # type: str, str | List[str]
        if isinstance(files, str):
            files = [files]

        # TODO: make relative to manifest file
        file_paths = []
        for file in files:
            file_path = pathlib.Path(file)
            # allow for globbing file names makes generating
            # a manifest for the ingest scripts easier
            if "*" in file:
                globbed = file_path.parent.glob(file_path.name)
                file_paths.extend(list(globbed))
            else:
                file_paths.append(file_path)

        for file_path in file_paths:
            rows: List[dict] = []

            # skip empty files
            if file_path.stat().st_size == 0:
                continue

            # file should be in jsonl format
            # which is just each table row as json on its own line
            lines_str = file_path.read_text()
            if len(lines_str) > 0:
                sub_rows = load_lines_from_str(lines_str)
                rows.extend(sub_rows)

            ingest_jsonl_rows(table_name, rows)

    return list(manifest_dict.keys())


def ingest_from_manifest_file(manifest_path: str | Path) -> List[str]:
    """
    Call ingest_from_manifest for a given file path
    """

    # currently json file but could also do yaml
    path = Path(manifest_path).resolve()
    if path.suffix in [".yaml", ".yml"]:
        manifest_dict = yaml.safe_load(path.read_text())
    else:
        manifest_dict = json.loads(path.read_text())
    return ingest_from_manifest(manifest_dict)


# shebang + print commands
BASH_HEADER = "#!/bin/sh\n\nset -xu\n\n"


class ExportCommandFormat(CaseInsensitiveEnum):
    """
    Steampipe standalone export command format.
    Standalone indicates the command should use steampipe_export_aws.
    Query indicates the command should use steampipe query.

    The difference here is that the Query format allows you to re-use existing
    Steampipe configuration files like your workspace.spc and aws.spc files.
    However, the Query export does not support JSONL output, only JSON, so you need to
    use an external tool like jq to  format the output. This is handlded in
    generate_standalone_export_commands.
    """

    Standalone = auto()
    Query = auto()


# TODO: manifest class
def generate_standalone_export_commands(
    cmd_format: ExportCommandFormat = ExportCommandFormat.Standalone,
) -> Tuple[dict, ExportBashScript]:
    """
    Generate a Bash script that will export all tables used by nodes and edges.
    """

    manifest = {}
    script = ""
    script += BASH_HEADER
    # fakes excluded as they do not align to real tables
    node_tables = [node.table for node in nodes(include_fakes=False)]
    # includes org tables regardless of Neph settings as this will generate
    # a script that runs out-of-band
    edge_tables = [edge.table for edge in get_subclasses(AssocRelationship)]
    for table in [*node_tables, *edge_tables]:
        out_file = f"neph_{table}.jsonl"
        command = None
        match cmd_format:
            case ExportCommandFormat.Standalone:
                command = f"steampipe_export_aws {table} --output jsonl 1> {out_file}"
            case ExportCommandFormat.Query:
                command = f'steampipe query "select * from {Settings.steampipe_aggregator}.{table}" --output json 1> {out_file}'
            case _:
                pass
        script += command
        script += "\n"
        manifest[table] = [out_file]
    if cmd_format == ExportCommandFormat.Query:
        # convert the json files into jsonl files
        script += """for jsonfile in *.json; do jq -c ".rows[]" "$jsonfile" 1> "${jsonfile}l"; done;"""
        script += "\n"

    return manifest, script
