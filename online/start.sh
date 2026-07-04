#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TROS_SETUP="${ARGUS_TROS_SETUP:-/opt/tros/humble/setup.bash}"
TROS_WORKSPACE="${ARGUS_TROS_WORKSPACE:-$HOME/ws}"

if [[ -f "$TROS_SETUP" ]]; then
  # shellcheck disable=SC1090
  source "$TROS_SETUP"
fi

if [[ -f "$TROS_WORKSPACE/install/local_setup.bash" ]]; then
  # shellcheck disable=SC1091
  source "$TROS_WORKSPACE/install/local_setup.bash"
fi

cd "$APP_DIR"
exec python3 app.py
