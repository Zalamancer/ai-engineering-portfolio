#!/usr/bin/env bash
# Creates the single Lightsail instance for the agent demo (us-east-1, small_3_0 = $12/month), SSH-only firewall,
# static IP, then runs deploy/server_setup.sh on it. Idempotent: re-running updates the code on an existing instance.
# Costs start the moment the instance exists — run scripts/aws_teardown.sh to stop them.
set -euo pipefail
A="${AWS_CLI:-$HOME/.local/bin/aws}"
NAME="${AO_INSTANCE_NAME:-agentops-1}"; REGION=us-east-1; ZONE=us-east-1a; BUNDLE=small_3_0; BLUEPRINT=ubuntu_22_04
KEY="$HOME/.ssh/lightsail-$REGION.pem"; REPO="https://github.com/Zalamancer/ai-engineering-portfolio.git"
cd "$(dirname "$0")/.."

if [ ! -f "$KEY" ]; then
  $A lightsail download-default-key-pair --region $REGION --query privateKeyBase64 --output text > "$KEY"; chmod 600 "$KEY"
fi
if ! $A lightsail get-instance --region $REGION --instance-name "$NAME" >/dev/null 2>&1; then
  echo "creating $NAME ($BUNDLE, $BLUEPRINT) ..."
  $A lightsail create-instances --region $REGION --instance-names "$NAME" --availability-zone $ZONE --blueprint-id $BLUEPRINT --bundle-id $BUNDLE \
     --tags key=project,value=ai-engineering-portfolio key=owner,value=agentops-deploy >/dev/null
  until [ "$($A lightsail get-instance --region $REGION --instance-name "$NAME" --query 'instance.state.name' --output text)" = "running" ]; do sleep 10; done
  # SSH only — the API/console are reached through an SSH tunnel, never exposed publicly
  $A lightsail put-instance-public-ports --region $REGION --instance-name "$NAME" --port-infos fromPort=22,toPort=22,protocol=tcp >/dev/null
  $A lightsail allocate-static-ip --region $REGION --static-ip-name "$NAME-ip" >/dev/null 2>&1 || true
  $A lightsail attach-static-ip --region $REGION --static-ip-name "$NAME-ip" --instance-name "$NAME" >/dev/null
fi
IP=$($A lightsail get-static-ip --region $REGION --static-ip-name "$NAME-ip" --query 'staticIp.ipAddress' --output text)
echo "instance $NAME at $IP"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 ubuntu@$IP"
until $SSH true 2>/dev/null; do sleep 5; done
scp -q -i "$KEY" -o StrictHostKeyChecking=accept-new deploy/server_setup.sh deploy/agentops.env.example ubuntu@$IP:/tmp/
$SSH "chmod +x /tmp/server_setup.sh && REPO=$REPO sudo -E /tmp/server_setup.sh"
echo
echo "done. open a tunnel and use it locally:"
echo "  ssh -i $KEY -N -L 8010:127.0.0.1:8010 -L 8501:127.0.0.1:8501 ubuntu@$IP"
echo "  then http://localhost:8501 (console) and http://localhost:8010/docs (API)"
