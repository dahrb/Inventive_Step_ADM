#!/bin/bash
# run.sh  — launch the ADM Results Explorer Streamlit app
# Usage:  bash webapp/run.sh [port]
# Run from the ADM_JURIX root directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${1:-8501}"

cd "$ROOT_DIR"

# ── load miniforge / conda ────────────────────────────────────────────────────
if ! command -v conda &>/dev/null; then
    module load miniforge3 2>/dev/null || true
fi

# ── install webapp deps if needed ─────────────────────────────────────────────
echo "[run.sh] Checking dependencies…"
conda run -n base pip install -q --upgrade streamlit plotly pandas networkx pythonds pydot

# ── launch ────────────────────────────────────────────────────────────────────
echo "[run.sh] Starting Streamlit on port $PORT …"
echo "[run.sh] Open: http://localhost:$PORT"
echo ""

conda run -n base streamlit run webapp/app.py \
    --server.port "$PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
