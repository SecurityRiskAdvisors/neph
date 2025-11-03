# Neo4j Triggers

Neph can listen for node creation events in Neo4j then trigger analysis workflows via its CDC functionality. The CDC is HTTP API server that listens for requests from Neo4j containing new node JSON data. It works by installing an [APOC trigger](https://neo4j.com/docs/apoc/current/background-operations/triggers/) in the database.

***Note: The CDC is largely experimental and should be avoided in most cases. Special care should be exercised when using it.***

## CLI

The API server can be started via

```
neph cdc
```

# Configuration

The following configuration options control the CDC functionality:

|Name|Description|Default|
|---|---|---|
|cdc_trigger|Name of trigger installed in Neo4j|neph_cdc|
|cdc_host|API hostname used in trigger and dby server|localhost|
|cdc_proto|API protocol used in trigger|http|
|cdc_uri|API path used in trigger and by server|/cdc|
|cdc_port|API server port used in trigger and by server|9003|
|use_cdc|Disable running analysis workflows during data ingest and instead have CDC run analysis|False|

# Workflow

The CDC uses the following workflow:

1. Run enrichments on the node instance
2. Generate the base relationships tied to the node's type (e.g. EC2Instance, IamUser, etc)
3. Generate leads for the node's type

If you set use_cdc to `True`, this workflow will be run on each new node event the CDC receives.
If you set use_cdc to `False`, this workflow will be run as part of the ingest CLI commands. 
