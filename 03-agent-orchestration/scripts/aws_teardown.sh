#!/usr/bin/env bash
# Deletes everything scripts/aws_deploy.sh created, then lists anything that could still bill.
set -uo pipefail
A="${AWS_CLI:-$HOME/.local/bin/aws}"; NAME="${AO_INSTANCE_NAME:-agentops-1}"; REGION=us-east-1
echo "backing up the run database first (if reachable) ..."
"$(dirname "$0")/aws_backup.sh" || echo "  (backup skipped)"
$A lightsail delete-instance --region $REGION --instance-name "$NAME" && echo "instance $NAME deleted"
$A lightsail release-static-ip --region $REGION --static-ip-name "$NAME-ip" && echo "static ip released"
for lg in $($A logs describe-log-groups --region $REGION --log-group-name-prefix agentops --query 'logGroups[].logGroupName' --output text 2>/dev/null); do
  $A logs delete-log-group --region $REGION --log-group-name "$lg" && echo "log group $lg deleted"; done
echo
echo "=== anything left that can bill (should all be empty) ==="
echo "instances:";  $A lightsail get-instances --region $REGION --query 'instances[].name' --output text
echo "static ips:"; $A lightsail get-static-ips --region $REGION --query 'staticIps[].name' --output text
echo "snapshots:";  $A lightsail get-instance-snapshots --region $REGION --query 'instanceSnapshots[].name' --output text
echo "log groups:"; $A logs describe-log-groups --region $REGION --query 'logGroups[].logGroupName' --output text
echo "s3 buckets:"; $A s3 ls
echo "budget 'portfolio-20-monthly' is kept on purpose (free); delete with: aws budgets delete-budget --account-id <id> --budget-name portfolio-20-monthly"
