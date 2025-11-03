# Neph CLI

## Global settings

```
neph [-h] [--settings Path] [--load-plugins | --no-load-plugins]

options:
  -h, --help            show this help message and exit
  --settings Path       Override default (".env") settings file (default: None)
  --load-plugins, --no-load-plugins
                        Load 3rd-party plugins (default: True)
```

## Ingest

### SQL

```
neph ingest sql [-h] [--mode {bulk,single}] [--create-fixtures | --no-create-fixtures] [--type {node,table}] [--target str]

options:
  --mode {bulk,single}  Ingestion mode (required)
  --create-fixtures, --no-create-fixtures
                        For bulk mode, create fixture nodes (default: True)
  --type {node,table}   For single mode, node type or Steampipe table to ingest (default: None)
  --target str          For single mode, target node/table (default: None)
```

Ingest data into Neo4j from the Steampipe database via the SQL connection. 
Data can ingested on a per-node basis or in bulk for all nodes. 
When doing bulk ingest, you can pass `--create-fixtures` to also create fixture nodes, which are used to represent
shared components like AWS Services, wildcards, etc. These fixture nodes are required for some relationships to be populated.
When ingesting single targets, you can ingest based on either the Steampipe table name or the node label. 
For example, if ingesting EC2 instances, you can specify the target as either `EC2Instance` (node label) or `aws_ec2_instance` (table).

### JSONL

```
neph ingest jsonl [-h] [--manifest Path] [--jsonl Path] [--table str]

options:
  --manifest Path  Path to manifest file (default: None)
  --jsonl Path     Path to JSONL file (default: None)
  --table str      Table name for direct file import (default: None)
```

Ingest data into Neo4j from local JSONL files (see `Exporter` section below).
You can ingest either multiple files using a manifest or individual JSONL files.

To ingest using a manifest, pass `--manifest <path>`, where `<path>` is the path to the manifest JSON file.
The manifest file format a JSON file of key-values, where the key is the Steampipe table name and the value is
either a file path (or glob pattern) or list of file paths (or glob patterns).

```
{
    "aws_iam_user": "exports/account_users*.jsonl"
    "aws_iam_role": [
        "exports/roles_1.jsonl",
        "exports/roles_2.jsonl",
    ]
}
```

Note: file names are relative to the controller's working directory.

To ingest using individual JSONL files, pass `--jsonl <path>` and `--table <name>`, where `<path>` is the path to the JSONL file and `<name>` is the Steampipe table name.

## Simulation

```
neph sim [-h] [--principal str] [--action str] [--resource str] [--raccount str] [--org-policies | --no-org-policies] [--write | --no-write]

options:
  --principal str       Source principal ARN or service ID (e.g. ec2.amazonaws.com (required)
  --action str          Action to simulate (required)
  --resource str        Resource to target (default: *)
  --raccount str        Override resource account (assumes same as principal) (default: None)
  --org-policies, --no-org-policies
                        Include AWS Organizations policies (SCPs/RCPs) in simulation (default: False)
  --write, --no-write   Write result to graph (default: False)
```

Run an IAM permission simulation for the given principal. If the action is allowed (and `--write` is True), a new
edge between the principal and the service of the resource is created for that action.

See [Simulator](Simulator.md) for more details.

## Exporter

```
neph exporter [-h] [--manifest Path] [--script Path] [--export nodes] [--format {query,standalone}]

options:
  --manifest Path       Path to output manifest (required)
  --script Path         Path to output shell script (required)
  --export nodes        Data export type (default: nodes)
  --format {query,standalone}
                        Export command format (default: standalone)
```

Generate a Bash script that can run the Steampipe CLI commands to enumerate all tables used by Neph and Neph plugins.
This is useful if you cannot perform enumeration activities on the Neph host (e.g. environment restrictions).

The `format` is either `query` or `standalone`. 
Standalone generates a script that will use the [Steampipe Export CLI](https://steampipe.io/docs/steampipe_export/install), which allow you to run Steampipe plugins (e.g. AWS) without a full Steampipe install/configuration. 
Query generates a script that will use the standard Steampipe CLI to run SQL `select` queries. 
This mode allows you to leverage your workspace/plugin configs, whereas Standalone requires you to configure the appropriate environment variables (example: setting the `AWS_PROFILE` for the AWS credential profile). 

## Workflow

### Base

```
neph workflow base [-h] [--node str]

options:
  --node str  Node type (required)
```

Run the base workflow (enrich -> relationships -> leads) for a given node type (e.g. EC2Instance, IamUser)

## Fanout

```
neph fanout [-h] [--arn str] [--strategy str] [--include-resources | --no-include-resources]

options:
  --arn str             Source principal ARN (required)
  --strategy str        Fanout strategy name (required)
  --include-resources, --no-include-resources
                        For permissions strategies, include resource ARN templates for each returned action (default: True)
```

Run the specified fanout strategy. 
Fanouts are basic permissions heuristic checks similar to Leads and can be used to identify potential next steps from a given principal.

Builtin strategies:

- `EC2AccessFanout` : Look for alternative EC2 access methods (SSM, EC2 instance connect)
- `CredentialAccessFanout` : Look for API methods that return some type of credential
- `DirectPrivescFanout` : Check if a user has permissions that could allow direct privilege escalation
- `ServicesFanout` : List of allowed services the principal can potentially access

## Report

```
neph report [-h] [--format csv] [--outfile {Path,Path}] [--report str]

options:
  --format csv          Report format (default: csv)
  --outfile {Path,Path}
                        Path to output file (required)
  --report str          Report to run (required)
```

Run the specified report and save it to a file in the given format. 

Supported output formats:

- CSV

## Misc

### Database

```
neph misc db [-h] --connections

options:
  --connections         Print number of connections not yet ready for use
```

## CDC

```
neph cdc
```

Starts the CDC server. See [CDC](Triggers.md).

## Inspect

```
neph inspect [-h] [--type {node,edge,enrichment,fanout,lead,report}]

options:
  --type {node,edge,enrichment,fanout,lead,report}
                        Object type to list (required)
```

Inspect the subclasses of the given type. Types include: nodes, edges, node enrichments, discovery fanouts, edge leads, and node property reports.

Output will include corresponding class docstrings in output for all types except nodes.
If plugin are installed (and also not disabled in the settings), classes from plugins will also appear in output.

## Path

### Left-to-right

```
neph path l2r [-h] [--start str] [--end str] [--add | --no-add] [--promote | --no-promote] [--relation str]

options:
  --start str           Start node specifier (required)
  --end str             End node specifier (required)
  --add, --no-add       Add a relation of the given type (default: False)
  --promote, --no-promote
                        Promote a lead of the given type (default: False)
  --relation str        Relationship type to add (default: None)
```

Add/query left-to-right relationships between two nodes.

Nodes should be specified using the format: `<node label>|<node id property>`. For example, an IAM User's node label is `IamUser` and its node ID property is its `arn`, so you would specify it like `IamUser|arn:aws:iam::123456789012:user/user1`. 

If you are querying relationships, results will include paths with any number of hops between nodes, not just direct relationships. However, you can only add direct relationships.

If you are adding a relationship between nodes, you must specify both `--add` and `--relation <relationship type>`.

You can alternatively specify `--promote` instead of `--add` to promote leads of the given relationship type between the two nodes.

### Leads

```
neph path leads [-h] [--all | --no-all] [--node str]

options:
  --all, --no-all  Generate all lead types (default: False)
  --node str       Node type (required)
  --lead str       Lead type (required)
```

Generate leads for one/all node/lead types.

Specifying `--node` with the node label (e.g. `EC2Instance`) will generate leads for a given node type.

Specifying `--lead` with the lead type (e.g. `RoleTrustPolicyLead`) will generate only that lead type. Use the `inspect` subcommand to list available types (details above).

Specifying `--all` will generate all lead types.

You can only specify one of the three options at a time. 

This subcommand will temporarily override the `generate_leads` setting to be True.

