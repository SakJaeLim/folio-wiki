#!/usr/bin/env bash
# Pinned single-process engine for Linux/WSL. Needs git, Go, a C compiler, SQLite headers and Ollama.
set -euo pipefail
engine_dir=${FOLIO_ENGINE_DIR:-"$PWD/.state/weknora"}
case "$engine_dir" in /*) ;; *) engine_dir="$PWD/$engine_dir";; esac
commit=f17ee8a8da901bd658a4cb25f40b5fd41adbfdd7
if [ ! -d "$engine_dir/.git" ]; then
  mkdir -p "$(dirname "$engine_dir")"
  git clone --quiet --depth 1 --branch v0.9.0 https://github.com/Tencent/WeKnora.git "$engine_dir"
fi
cd "$engine_dir"
test "$(git rev-parse HEAD)" = "$commit" || { echo "Unexpected WeKnora commit"; exit 1; }
if [ ! -x WeKnora-lite ]; then
  export GOTOOLCHAIN=auto EDITION=lite CGO_ENABLED=1
  export CGO_CFLAGS="-Wno-deprecated-declarations"
  go build -p 3 -tags sqlite_fts5 -ldflags="-w -s $(bash scripts/get_version.sh ldflags) -X google.golang.org/protobuf/reflect/protoregistry.conflictPolicy=warn" -o WeKnora-lite ./cmd/server
fi
umask 077
if [ ! -f .env.lite ]; then
  cp .env.lite.example .env.lite
  printf '\nSYSTEM_AES_KEY=%s\nJWT_SECRET=%s\n' "$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')" "$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')" >> .env.lite
fi
export SERVER_PORT=${FOLIO_ENGINE_PORT:-8794} SERVER_HOST=127.0.0.1
export OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://127.0.0.1:11434}
export WEKNORA_LANGUAGE=${WEKNORA_LANGUAGE:-ko-KR}
chat=${FOLIO_OLLAMA_CHAT:-qwen2.5:3b}
[[ "$chat" =~ ^[a-zA-Z0-9_.:/-]+$ ]] || { echo "Invalid Ollama model name"; exit 1; }
if [ ! -e config/builtin_models.yaml ]; then
  cat > config/builtin_models.yaml <<EOF
builtin_models:
  - id: builtin-lab-chat
    type: KnowledgeQA
    source: local
    is_default: true
    name: "$chat"
  - id: builtin-lab-embedding
    type: Embedding
    source: local
    is_default: true
    name: nomic-embed-text
    parameters:
      embedding_parameters:
        dimension: 768
EOF
fi
export GIN_MODE=release LOG_LEVEL=info
exec ./WeKnora-lite
