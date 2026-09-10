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
