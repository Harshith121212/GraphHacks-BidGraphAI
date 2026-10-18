#!/usr/bin/env bash
set -e

echo "================================================================="
echo "   BidGraphAI: FalkorDB + MCP Tender Intelligence Engine        "
echo "================================================================="

# Check if FalkorDB is reachable
echo "[1/3] Verifying FalkorDB connectivity..."
python3 -c "
import os, sys
from db.connection import get_graph
try:
    g = get_graph()
    g.query('RETURN 1')
    print('>> FalkorDB connected successfully.')
except Exception as e:
    host = os.environ.get('FALKORDB_HOST', 'localhost')
    port = os.environ.get('FALKORDB_PORT', '6379')
    print(f'>> Warning: FalkorDB unreachable at {host}:{port}: {e}')
" || true

# Run seed if empty or requested
if [ "${AUTO_SEED:-false}" = "true" ]; then
    echo "[2/3] AUTO_SEED=true: Checking benchmark graph initialization (memory preserved if already seeded)..."
    python3 -m db.seed_graph || true
else
    echo "[2/3] Skipping seed (AUTO_SEED not set to true)."
fi

# Start FastAPI application
PORT="${PORT:-8000}"
echo "[3/3] Launching FastAPI server & Frontend Dashboard on 0.0.0.0:${PORT}..."
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT}"
