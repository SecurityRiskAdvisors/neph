#!/usr/bin/env bash

# expects steampipe_export_aws exporter in either PATH or current directory
# other tools required: jq

set -xu

# load identity stores
steampipe_export_aws aws_ssoadmin_instance --output jsonl 1> aws_ssoadmin_instance.jsonl
# load permission sets
steampipe_export_aws aws_ssoadmin_permission_set --output jsonl 1> aws_ssoadmin_permission_set.jsonl
# load accounts
steampipe_export_aws aws_organizations_account --select id 1> accounts.txt
mv "accounts.txt" "accounts.txt.bak"
tail -n +2 "accounts.txt.bak" 1> "accounts.txt"

for identity_store in $(jq -r .identity_store_id aws_ssoadmin_instance.jsonl)
do
  # load identity store users
  steampipe_export_aws aws_identitystore_user --where "identity_store_id='${identity_store}'" --output jsonl 1> "aws_identitystore_user_${identity_store}.jsonl"

  # load identity store groups
  steampipe_export_aws aws_identitystore_group --where "identity_store_id='${identity_store}'" --output jsonl 1> "aws_identitystore_group_${identity_store}.jsonl"
  # load identity store group memberships
  steampipe_export_aws aws_identitystore_group_membership --where "identity_store_id='${identity_store}'" --output jsonl 1> "aws_identitystore_group_membership_${identity_store}.jsonl"
done

arn_ct=0
for arn in $(jq -r .arn aws_ssoadmin_permission_set.jsonl)
do
  # load identity store policy attachments
  steampipe_export_aws aws_ssoadmin_managed_policy_attachment --where "permission_set_arn='${arn}'" --output jsonl 1> "aws_ssoadmin_managed_policy_attachment_${arn_ct}.jsonl"
  ((arn_ct++))

  account_ct=0
  while ((account_ct++)); IFS= read -r line
  do
    # load identity store account assignments
    steampipe_export_aws aws_ssoadmin_account_assignment --where "permission_set_arn='${arn}'" --where "target_account_id='${line}'" --output jsonl 1> "aws_ssoadmin_account_assignment_${arn_ct}_${account_ct}_${line}.jsonl"
  done < accounts.txt
done
