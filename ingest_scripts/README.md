# AWS Identity Center / SSO ingestion tools

Standalone ingestion tools to collect aws_identitystore_* and aws_ssoadmin_* tables.

Requires the [steampipe_export_aws](https://steampipe.io/docs/steampipe_export/install) and `jq`.

## Warning

This script will take a long time to run as it queries all combinations of permission sets and account IDs. If you are assuming a role, be careful about the token expiring prior to completion of the collection.


## Other resources

The Steampipe docs for Org collection (https://steampipe.io/docs/guides/aws-orgs) 
and linked scripts (https://github.com/turbot/steampipe-samples/tree/main/all/aws-organizations-scripts) 
can be used to generate the AWS credential file(s) for multi-account collection. 
