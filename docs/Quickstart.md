# Quickstart

This document describes how to run Neph from start to finish against a single AWS account.
This guide will not use the CDC service.

## Step 0 : Setup

1. Configure your AWS credential profile
2. Have Docker and Docker Compose (or something compatible) installed 
3. Have Neph installed

## Step 1 : Compose

Modify the Steampipe service (`steampipe`) in the provided Compose file (`docker-compose.example.yml`)

```yaml
volumes:
# ...
- ./steampipe/aws.spc:/home/steampipe/.steampipe/config/aws.spc
environment:
# ...
  STEAMPIPE_PASSWORD: steampipe
```

Configure the Steampipe database service password. This will be used later in your Neph env file.

Configure your Steampipe AWS connections file. 
By default, the service will mount the local file `./steampipe/aws.spc`. 
You can edit this directly or copy it then update the mount. 
The file should look like:

```
connection "aws" {
    plugin = "aws"
    profile = "steampipe"
    regions = ["us-east-*"]
    ignore_error_codes = ["AccessDenied", "AccessDeniedException", "NotAuthorized", "UnauthorizedOperation", "UnrecognizedClientException", "AuthorizationError"]
}
```

Replace `steampipe` in `profile = "steampipe"` with your AWS credential profile name. See [Collection.md](Collection.md) for more details.

Then change the Neo4j auth details for the Neo4j service (`neo4j`):

```yaml
environment:
# ...
  NEO4J_AUTH: neo4j/pleasechangeme
```

*Note: the [JupyterLab](Jupyter.md) and [CDC](Triggers.md) services in Compose are entirely optional.
If you do not plan to use them, you can remove them from the file.
The below Compose command assumes you only want to start the core services.*

Finally, start the services

> `docker compose -f <compose file> up -d simulator steampipe neo4j`

## Step 2 : Configure Neph

Configure your Neph env file (`.env` in your working directory):

```
steampipe_password=<password>
steampipe_host=steampipe
neo4j_host=localhost
neo4j_password=<password>
simulator_url=http://localhost:3000/
steampipe_aggregator=aws
generate_leads=False
```

Modify `steampipe_password=<password>` and `neo4j_password=<password>` to match the passwords from step 1.
If you modified the AWS connection name in `aws.spc`, also update `steampipe_aggregator=aws` to match.

If the target AWS account is the Organization root account, you should add the line `load_aws_org=True` to collect Organization data.

## (Optional) Step 3 : Plugins

If you plan to use plugin, make sure they are installed in the same (virtual-)environment as Neph (see [Plugins.md](Plugins.md))

## Step 4 : Collection

To collect data, run:

> `neph ingest sql --mode bulk --create-fixtures`

(Optional) If you are collecting Organization and/or SSO/IAM Identity Center data, you should run the ingest scripts located in [ingest_scripts/](../ingest_scripts/) to collect additional data.
These scripts will output files that can be ingested using `neph ingest jsonl`

## Step 5 : Leads

After collection is complete, generate leads:

> `neph path leads --all`

## Step 6 : Querying

Finally, you can start inspecting/querying data from the Neo4j UI at `http://localhost:7474/`. For example queries, see [Queries.md](Queries.md). 

You can also interact with Neo4j from Jupyter (see [Jupyter.md](Jupyter.md)).
