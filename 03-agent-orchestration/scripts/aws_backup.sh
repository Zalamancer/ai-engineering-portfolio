#!/usr/bin/env bash
# Copies the server's run database + traces to S3 (bucket created on first use, 30-day expiry).
set -euo pipefail
A="${AWS_CLI:-$HOME/.local/bin/aws}"; NAME="${AO_INSTANCE_NAME:-agentops-1}"; REGION=us-east-1
KEY="$HOME/.ssh/lightsail-$REGION.pem"; ACC=$($A sts get-caller-identity --query Account --output text); BUCKET="agentops-portfolio-$ACC"
IP=$($A lightsail get-static-ip --region $REGION --static-ip-name "$NAME-ip" --query 'staticIp.ipAddress' --output text)
TMP=$(mktemp -d); scp -q -i "$KEY" ubuntu@$IP:/opt/agentops/03-agent-orchestration/data/agentops.db "$TMP/agentops-$(date +%Y%m%d-%H%M).db"
$A s3api head-bucket --bucket "$BUCKET" 2>/dev/null || { $A s3 mb "s3://$BUCKET" --region $REGION >/dev/null;
  $A s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration '{"Rules":[{"ID":"expire","Status":"Enabled","Filter":{"Prefix":""},"Expiration":{"Days":30}}]}';
  $A s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true; }
$A s3 cp "$TMP"/*.db "s3://$BUCKET/backups/" --only-show-errors && echo "backup uploaded to s3://$BUCKET/backups/"
rm -rf "$TMP"
