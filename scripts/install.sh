#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." ; pwd)"
AGENT_SCRIPT="${PROJECT_ROOT}/scripts/local_agent.py"

if [[ ! -f "${AGENT_SCRIPT}" ]]; then
  echo "local_agent.py not found at ${AGENT_SCRIPT}" >&2
  exit 1
fi

OS_NAME="$(uname -s)"
ARCH="$(uname -m)"
case "${OS_NAME}" in
  Linux*) PLATFORM="linux" ;;
  Darwin*) PLATFORM="macos" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  *) PLATFORM="unknown" ;;
esac

echo "Detected platform: ${PLATFORM} (${ARCH})"

if [[ "${PLATFORM}" == "windows" ]]; then
  echo "Use PowerShell startup scripts on Windows: ./scripts/start_all.ps1"
  echo "Or run local agent directly: python scripts/local_agent.py"
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install Python 3.10+ and retry." >&2
  exit 1
fi

if [[ "${PLATFORM}" == "linux" && -r /proc/meminfo ]]; then
  MEM_TOTAL_KB="$(grep -i '^MemTotal:' /proc/meminfo | awk '{print $2}')"
  echo "Linux /proc detected. MemTotal=${MEM_TOTAL_KB}KB"
fi

if command -v sysctl >/dev/null 2>&1; then
  CPU_MODEL="$(sysctl -n machdep.cpu.brand_string 2>/dev/null ; true)"
  [[ -n "${CPU_MODEL}" ]] && echo "CPU: ${CPU_MODEL}"
fi

python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install psutil >/dev/null

echo "Starting Resilo local agent at http://127.0.0.1:9090/metrics"
exec python3 "${AGENT_SCRIPT}"
