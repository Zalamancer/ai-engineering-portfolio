#!/usr/bin/env bash
# Runs ON the instance as root: installs uv, clones/updates the repo, installs deps, seeds data, installs systemd services
# bound to localhost only, ships journal logs to CloudWatch (7-day retention) if the agent can be installed.
set -euo pipefail
REPO="${REPO:-https://github.com/Zalamancer/ai-engineering-portfolio.git}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git curl python3-venv >/dev/null
if [ ! -d /opt/agentops ]; then git clone -q "$REPO" /opt/agentops; else git -C /opt/agentops pull -q; fi
chown -R ubuntu:ubuntu /opt/agentops
sudo -u ubuntu bash -c 'command -v ~/.local/bin/uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null'
sudo -u ubuntu bash -c 'cd /opt/agentops/03-agent-orchestration && ~/.local/bin/uv sync -q && ~/.local/bin/uv run python scripts/seed_demo_db.py'
[ -f /etc/agentops.env ] || cp /tmp/agentops.env.example /etc/agentops.env; chmod 600 /etc/agentops.env
mkdir -p /var/log/agentops && chown ubuntu:ubuntu /var/log/agentops
# CloudWatch agent: ships worker/api logs to log group "agentops" (7-day retention) using the Bedrock-only profile
# (that IAM user also has CloudWatchAgentServerPolicy). Skipped silently if the profile is not installed yet.
if [ -f /home/ubuntu/.aws/credentials ]; then
  dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1 || { curl -sSL -o /tmp/cw.deb https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb && dpkg -i /tmp/cw.deb >/dev/null; }
  printf '[credentials]\n  shared_credential_profile = "bedrock"\n  shared_credential_file = "/home/ubuntu/.aws/credentials"\n' > /opt/aws/amazon-cloudwatch-agent/etc/common-config.toml
  cat > /opt/aws/amazon-cloudwatch-agent/etc/agentops.json <<'J'
{"agent": {"region": "us-east-1", "run_as_user": "root"},
 "logs": {"logs_collected": {"files": {"collect_list": [
   {"file_path": "/var/log/agentops/worker.log", "log_group_name": "agentops", "log_stream_name": "worker", "retention_in_days": 7},
   {"file_path": "/var/log/agentops/api.log", "log_group_name": "agentops", "log_stream_name": "api", "retention_in_days": 7}]}}}}
J
  /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m onPremise -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/agentops.json >/dev/null 2>&1 || true
fi
for svc in api worker console testtarget; do
  case $svc in
    api) CMD="uvicorn agentops.api:app --host 127.0.0.1 --port 8010";;
    worker) CMD="python -m agentops.worker";;
    console) CMD="streamlit run agentops/ui.py --server.headless true --server.address 127.0.0.1 --server.port 8501";;
    testtarget) CMD="uvicorn agentops.testtarget:app --host 127.0.0.1 --port 8099";;
  esac
  cat > /etc/systemd/system/agentops-$svc.service <<UNIT
[Unit]
Description=agentops $svc
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/opt/agentops/03-agent-orchestration
EnvironmentFile=/etc/agentops.env
ExecStart=/home/ubuntu/.local/bin/uv run $CMD
StandardOutput=append:/var/log/agentops/$svc.log
StandardError=append:/var/log/agentops/$svc.log
Restart=always
RestartSec=5
MemoryMax=1400M
[Install]
WantedBy=multi-user.target
UNIT
done
systemctl daemon-reload
for svc in api worker console testtarget; do systemctl enable -q agentops-$svc && systemctl restart agentops-$svc; done
sleep 8; systemctl --no-pager --type=service | grep agentops || true
echo "memory:"; free -m | head -2
echo "server setup done"
