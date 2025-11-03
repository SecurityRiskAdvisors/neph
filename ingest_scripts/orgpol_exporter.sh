#!/usr/bin/env bash

# expects steampipe_export_aws exporter in either PATH or current directory
# other tools required: jq

set -xu

# load accounts
steampipe_export_aws aws_organizations_account --select id 1> accounts.txt
mv "accounts.txt" "accounts.txt.bak"
tail -n +2 "accounts.txt.bak" 1> "accounts.txt"

steampipe_export_aws aws_organizations_policy --where "type in ('SERVICE_CONTROL_POLICY','RESOURCE_CONTROL_POLICY')" --output jsonl 1> "aws_organizations_policy.jsonl"

while IFS= read -r line
do
  # load organization policy attachments

  # scps
  steampipe_export_aws aws_organizations_policy_target --where "type='SERVICE_CONTROL_POLICY'" --where "target_id='${line}'" --output jsonl 1> "aws_organizations_policy_target_scps_${line}.jsonl"

  # rcps
  steampipe_export_aws aws_organizations_policy_target --where "type='RESOURCE_CONTROL_POLICY'" --where "target_id='${line}'" --output jsonl 1> "aws_organizations_policy_target_rcps_${line}.jsonl"
done < accounts.txt
