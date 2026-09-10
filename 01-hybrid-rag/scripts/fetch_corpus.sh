#!/usr/bin/env bash
# Re-creates data/raw at the exact pinned commits listed in data/raw/MANIFEST.md.
set -euo pipefail
cd "$(dirname "$0")/../data/raw"
mkdir -p _src rfc
clone() { # name url subdir commit
  if [ ! -d "_src/$1/.git" ]; then
    git clone -q --filter=blob:none --sparse "$2" "_src/$1"
  fi
  (cd "_src/$1" && git sparse-checkout set --no-cone "$3" 'LICENSE*' pyproject.toml >/dev/null && git fetch -q --depth 1 origin "$4" && git checkout -q "$4")
}
clone fastapi  https://github.com/fastapi/fastapi.git  docs/en/docs 50113da16fec53b66b80d75e80a89296de4fa5a5
clone starlette https://github.com/encode/starlette.git docs        f03f65c2f98c592773d691b4d309c68b83e568ef
clone uvicorn  https://github.com/encode/uvicorn.git   docs         fa324a415364563cf45908966435e2480a6b46bf
cd rfc
[ -f rfc9110-http-semantics.pdf ]  || curl -sSL -o rfc9110-http-semantics.pdf  https://www.rfc-editor.org/rfc/rfc9110.pdf
[ -f rfc9112-http11.txt ]          || curl -sSL -o rfc9112-http11.txt          https://www.rfc-editor.org/rfc/rfc9112.txt
[ -f rfc9457-problem-details.txt ] || curl -sSL -o rfc9457-problem-details.txt https://www.rfc-editor.org/rfc/rfc9457.txt
[ -f rfc6455-websocket.html ]      || curl -sSL -o rfc6455-websocket.html      https://www.rfc-editor.org/rfc/rfc6455.html
[ -f rfc6265-http-cookies.html ]   || curl -sSL -o rfc6265-http-cookies.html   https://www.rfc-editor.org/rfc/rfc6265.html
echo "corpus ready"
