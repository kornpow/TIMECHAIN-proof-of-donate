#!/usr/bin/env bash
# test_payment.sh — simulate a Lightning payment webhook
#
# Sends a POST directly to the local webhook server with the same payload
# LNbits/lnurlp would send on a real payment. No real funds needed.
#
# Usage:
#   ./test_payment.sh          # default: 21 sats
#   ./test_payment.sh 100      # 100 sats → 100 seconds of music

set -euo pipefail

SATS="${1:-21}"
MSAT=$(( SATS * 1000 ))
WEBHOOK="http://localhost:8000"

echo ""
echo "=== Simulating ${SATS}-sat payment ==="

RESP=$(curl -sf -X POST "$WEBHOOK/webhook" \
  -H "Content-Type: application/json" \
  -d "{\"payment_hash\": \"test$(date +%s)\", \"amount\": $MSAT, \"comment\": \"test payment\", \"lnurlp\": \"test\"}" \
  2>&1)

echo "   Webhook response: $RESP"

sleep 2

HEALTH=$(curl -sf "$WEBHOOK/health" 2>/dev/null || echo '{"daemon":"unknown"}')
DAEMON=$(echo "$HEALTH" | python3 -c "import json,sys; print(json.load(sys.stdin).get('daemon','?'))")

echo ""
echo "=== Result ==="
echo "   Daemon status: $DAEMON"
echo "   Expected: ${SATS} seconds of music"
echo ""
echo "   To stop:      uv run main.py control stop"
echo "   To watch logs: ./start.sh logs"
