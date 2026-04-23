#!/usr/bin/env bash
# start.sh — manage the TIMECHAIN Proof of Donate stack
#
# Usage:
#   ./start.sh          # start everything
#   ./start.sh stop     # stop everything
#   ./start.sh status   # show what's running
#   ./start.sh logs     # tail all logs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LNBITS_PKG="$HOME/.local/share/uv/tools/lnbits/lib/python3.13/site-packages"

LNBITS_LOG="/tmp/lnbits.log"
WEBHOOK_LOG="/tmp/webhook.log"
DAEMON_LOG="/tmp/daemon.log"

LNBITS_PID_FILE="/tmp/timechain-lnbits.pid"
WEBHOOK_PID_FILE="/tmp/timechain-webhook.pid"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }

is_running() {
    local pid_file="$1"
    [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

stop_pid() {
    local pid_file="$1"
    local name="$2"
    if is_running "$pid_file"; then
        kill "$(cat "$pid_file")" 2>/dev/null
        yellow "Stopped $name."
    else
        echo "$name was not running."
    fi
    rm -f "$pid_file"
}

cmd_stop() {
    echo "Stopping TIMECHAIN stack..."
    stop_pid "$WEBHOOK_PID_FILE" "Webhook server"
    stop_pid "$LNBITS_PID_FILE"  "LNbits"
    if [[ -S "$SCRIPT_DIR/.bt-speaker.sock" ]]; then
        cd "$SCRIPT_DIR" && uv run main.py control stop 2>/dev/null || true
    fi
    green "Done."
}

cmd_status() {
    echo ""
    echo "=== TIMECHAIN stack ==="
    if is_running "$LNBITS_PID_FILE"; then
        green "  LNbits:  running (pid $(cat $LNBITS_PID_FILE))"
    else
        red   "  LNbits:  stopped"
    fi
    if is_running "$WEBHOOK_PID_FILE"; then
        green "  Webhook: running (pid $(cat $WEBHOOK_PID_FILE))"
    else
        red   "  Webhook: stopped"
    fi
    echo ""
    echo "=== Health ==="
    curl -sf http://127.0.0.1:5001/api/v1/health 2>/dev/null && echo "" \
        || red "  LNbits not responding on :5001"
    curl -sf http://127.0.0.1:8000/health 2>/dev/null && echo "" \
        || red "  Webhook not responding on :8000"
    echo ""
}

cmd_logs() {
    echo "Tailing logs — Ctrl-C to stop"
    tail -f "$LNBITS_LOG" "$WEBHOOK_LOG" "$DAEMON_LOG" 2>/dev/null
}

cmd_start() {
    echo ""
    echo "=== Starting TIMECHAIN Proof of Donate ==="

    # preflight
    if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
        red "ERROR: $SCRIPT_DIR/.env not found — copy .env.example and fill it in"
        exit 1
    fi
    if ! command -v uv &>/dev/null; then
        red "ERROR: uv not found — install from https://astral.sh/uv"
        exit 1
    fi
    if ! command -v blueutil &>/dev/null; then
        red "ERROR: blueutil not found — brew install blueutil"
        exit 1
    fi

    # sync credentials to LNbits package dir
    echo "Syncing .env and TLS cert to LNbits..."
    cp "$SCRIPT_DIR/.env" "$LNBITS_PKG/.env"
    [[ -f "$SCRIPT_DIR/lnd-tls.cert" ]] && cp "$SCRIPT_DIR/lnd-tls.cert" "$LNBITS_PKG/lnd-tls.cert"

    # start LNbits
    if is_running "$LNBITS_PID_FILE"; then
        yellow "LNbits already running (pid $(cat $LNBITS_PID_FILE))"
    else
        echo "Starting LNbits on :5001..."
        nohup bash -c "cd '$LNBITS_PKG' && uv tool run lnbits" >> "$LNBITS_LOG" 2>&1 &
        echo $! > "$LNBITS_PID_FILE"
        green "  LNbits pid $! — log: $LNBITS_LOG"
    fi

    # wait for LNbits
    echo -n "  Waiting for LNbits"
    for i in $(seq 1 30); do
        curl -sf http://127.0.0.1:5001/api/v1/health &>/dev/null && echo " ready." && break
        sleep 1 && echo -n "."
        if [[ $i -eq 30 ]]; then
            echo ""
            red "  WARNING: LNbits not ready after 30s — check $LNBITS_LOG"
        fi
    done

    # start webhook server
    if is_running "$WEBHOOK_PID_FILE"; then
        yellow "Webhook already running (pid $(cat $WEBHOOK_PID_FILE))"
    else
        echo "Starting webhook server on :8000..."
        nohup bash -c "cd '$SCRIPT_DIR' && uv run webhook.py" >> "$WEBHOOK_LOG" 2>&1 &
        echo $! > "$WEBHOOK_PID_FILE"
        green "  Webhook pid $! — log: $WEBHOOK_LOG"
    fi

    echo ""
    green "=== Stack is up ==="
    echo "  QR page:   http://localhost:8000/qr"
    echo "  LNbits UI: http://localhost:5001"
    echo ""
    echo "  ./start.sh stop    — stop everything"
    echo "  ./start.sh status  — check health"
    echo "  ./start.sh logs    — tail all logs"
    echo ""
}

cmd_play() {
    local secs="${2:-}"
    if [[ -n "$secs" ]]; then
        echo "Playing music for ${secs}s — Ctrl-C to stop"
        cd "$SCRIPT_DIR" && uv run main.py daemon \
            --mac 90-f2-60-a7-d1-12 \
            --file timechain-song_this-is-no-me-there-is-no-you.mp3 \
            --no-outlet \
            --duration "$secs"
    else
        echo "Playing music — Ctrl-C to stop"
        cd "$SCRIPT_DIR" && uv run main.py daemon \
            --mac 90-f2-60-a7-d1-12 \
            --file timechain-song_this-is-no-me-there-is-no-you.mp3 \
            --no-outlet
    fi
}

cmd_outlet() {
    local secs="${2:-5}"
    echo "Turning outlet ON for ${secs}s..."
    curl -sf "http://172.20.10.2/rpc/Switch.Set" -d '{"id":0,"on":true}' > /dev/null
    sleep "$secs"
    curl -sf "http://172.20.10.2/rpc/Switch.Set" -d '{"id":0,"on":false}' > /dev/null
    echo "Outlet off."
}

cmd_help() {
    echo ""
    echo "Usage: ./start.sh <command>"
    echo ""
    echo "Commands:"
    echo "  start             start LNbits + webhook server"
    echo "  stop              stop LNbits + webhook server"
    echo "  status            show running status and health"
    echo "  logs              tail all logs (Ctrl-C to exit)"
    echo "  play [seconds]    play the song (optional duration, default: full song)"
    echo "  outlet [seconds]  toggle outlet on for N seconds (default: 5)"
    echo "  help              show this message"
    echo ""
}

case "${1:-start}" in
    start)   cmd_start       ;;
    stop)    cmd_stop        ;;
    status)  cmd_status      ;;
    logs)    cmd_logs        ;;
    play)    cmd_play "$@"   ;;
    outlet)  cmd_outlet "$@" ;;
    help)    cmd_help        ;;
    *)
        cmd_help
        exit 1
        ;;
esac
