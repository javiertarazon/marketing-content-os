#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${HF_CLI:-}" ]]; then
  HF_COMMAND="$HF_CLI"
elif command -v hf >/dev/null 2>&1; then
  HF_COMMAND="$(command -v hf)"
elif [[ -x "${HOME}/.local/bin/hf" ]]; then
  HF_COMMAND="${HOME}/.local/bin/hf"
else
  echo "No se encontro HF CLI. Instala con: pipx install huggingface_hub" >&2
  exit 1
fi

IDENTITY="$("$HF_COMMAND" auth whoami --format json)"
USERNAME="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["user"])' <<<"$IDENTITY")"
SPACE_ID="${USERNAME}/marketing-script-generator"

echo "Creando/verificando el Space privado ZeroGPU ${SPACE_ID}"
"$HF_COMMAND" repos create "$SPACE_ID" \
  --type space \
  --sdk gradio \
  --private \
  --flavor zero-a10g \
  --exist-ok
"$HF_COMMAND" repos settings "$SPACE_ID" --type space --private
"$HF_COMMAND" spaces settings "$SPACE_ID" --hardware zero-a10g

echo "Publicando el generador Qwen3 en ${SPACE_ID}"
"$HF_COMMAND" upload "$SPACE_ID" "${ROOT}/apps/script-generator-space" . \
  --type space \
  --commit-message "Deploy private Qwen3 ZeroGPU script generator"

printf '\nSpace publicado: https://huggingface.co/spaces/%s\n' "$SPACE_ID"
echo "Revisa el build. El Space debe permanecer privado y usar ZeroGPU."
