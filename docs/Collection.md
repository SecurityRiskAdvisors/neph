# Customizing Collection

This document describes methods of customizing the data collection component for Neph.

## Compose

You can modify the Steampipe configuration by mounting Steampipe configurations files into the Steampipe container via Compose.

To modify the [workspace configuration](https://steampipe.io/docs/reference/config-files/workspace), mount your file at `/home/steampipe/.steampipe/config/workspace.spc`. To modify the [AWS configuration](https://hub.steampipe.io/plugins/turbot/aws#configuration), mount your file at `/home/steampipe/.steampipe/config/aws.spc`. Additionally, you can supplement the existing configuration files with new ones by mounting them adjacent to those files (`/home/steampipe/.steampipe/config/<file>`). Steampipe will load all `.spc` files in the config directory on startup.

### Rate limiting

If you find you are hitting AWS rate limits, you can add the following section to your workspace configurations:

```
plugin "aws" {
  limiter "aws_regional_rate_limit" {
    max_concurrency = <int>
    bucket_size = <int>
    fill_rate   = <int>
    scope       = ["connection", "region"]
  }
}
```

To modify the rate limits, adjust the max_concurrency, bucket_size, and fill_rate options. See https://steampipe.io/docs/guides/limiter for details.

### AWS Accounts

To collect from an AWS account using Steampipe, you must perform several configuration steps.

First, mount your AWS directory (`~/.aws`) into the container at `/home/steampipe/.aws/`.

For each account you want to collect from, add a connection to your mounted [AWS configuration](https://hub.steampipe.io/plugins/turbot/aws#configuration) file. An example AWS configuration file should look like:

```
connection "aws" {
  type        = "aggregator"
  plugin      = "aws"
  connections = ["aws*"]
}

connection "aws_1" {
    plugin = "aws"
    profile = "profile1"
    regions = ["*"]
    ignore_error_codes = ["AccessDenied", "AccessDeniedException", "NotAuthorized", "UnauthorizedOperation", "UnrecognizedClientException", "AuthorizationError"]
}

connection "aws_2" {
    plugin = "aws"
    profile = "profile2"
    regions = ["*"]
    ignore_error_codes = ["AccessDenied", "AccessDeniedException", "NotAuthorized", "UnauthorizedOperation", "UnrecognizedClientException", "AuthorizationError"]
}
```

Notice the `connections` property of the first block. The connections names need to match that pattern to be included in the aggregation. See https://steampipe.io/docs/managing/connections for details.

The `ignore_error_codes` can be used to configure which error codes are ignored during collection. This will allow the collection to continue collection in the event of an authorization error. For example, when collecting S3 bucket information, if you are not permitted to collect bucket policy information despite requesting it, this setting will determine whether the collection process silently skips those errors or breaks on them. Be careful as the above configuration essentially ignores all errors.

Steampipe loads connections asynchronously after startup. 
You will need to wait for them all to load before you query for data. 
Use the CLI command `neph misc db --connections` to check the readiness of the connections.

### Neph settings

Neph is the orchestrator for the collection operations. You can use a local settings file or environment variables to control the collection. A typical configuration file will look like so, assuming you are running Neph and Compose on the same host:

```
steampipe_password=password
steampipe_host=steampipe
neo4j_host=localhost
simulator_url=http://localhost:3000/
steampipe_aggregator=aws
```

The Neo4j and Simulator host information is relative to Neph, as Neph establishes a direct connection to those containers. The Steampipe host information is relative to Neo4j, as the SQL queries are performed via the JDBC connector from Neo4j. If you plan to use the CDC, you will also need to mount of copy of this configuration into the CDC container at `/app/.env` after adjusting the hostnames to be their container hostnames.

If you want to perform queries against individual AWS connections, you can modify the aggregator to be just that connection's name (example: `aws_1`).

