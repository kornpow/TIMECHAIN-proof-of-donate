"""
Webhook receiver for LNbits payment events.

LNbits fires a POST to /webhook when a payment is received via the lnurlp paylink.
On payment:
  - Pulses the Shelly outlet for 2 seconds
  - Optionally plays music via the bt-speaker daemon (1 sat = 1 second)

A fallback poller checks LNbits every 5s so payments are never missed even
if the LNbits→webhook call drops (e.g. LND invoice stream dropout over Tailscale).

Endpoints:
  POST /webhook   — called by LNbits on payment received
  GET  /health    — stack health: shelly, lnbits, lnd, daemon, seen_hashes
  GET  /qr        — fullscreen QR donation page
  GET  /invoice   — create a bolt11 invoice for a given sat amount

Run: uv run webhook.py
"""

import asyncio
import json
import socket
import subprocess
import time
import threading
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from ishelly.client import ShellyPlug
from ishelly.components.switch import SwitchSetParams
import uvicorn

app = FastAPI()

SHELLY_HOST = "172.16.4.55"
OUTLET_PULSE_SECONDS = 2

MP3_FILE = "timechain-song_this-is-no-me-there-is-no-you.mp3"
SPEAKER_MAC = "90-f2-60-a7-d1-12"

STATE_FILE = Path(__file__).parent / ".lnbits-state.json"
SOCKET_PATH = Path(__file__).parent / ".bt-speaker.sock"

# Set of payment hashes we've already acted on.
# Seeded at startup with all historical payments so we never replay history.
_seen_hashes: set[str] = set()


# ── Shelly outlet ─────────────────────────────────────────────────────────────

def pulse_outlet(seconds: float = OUTLET_PULSE_SECONDS) -> None:
    """Turn the Shelly outlet on, wait, then turn it off."""
    try:
        plug = ShellyPlug(SHELLY_HOST)
        plug.switch.set(SwitchSetParams(id=0, on=True))
        print(f"Outlet ON ({seconds}s)")
        time.sleep(seconds)
        plug.switch.set(SwitchSetParams(id=0, on=False))
        print("Outlet OFF")
    except Exception as e:
        print(f"[outlet] error: {e}")


# ── BT speaker daemon ─────────────────────────────────────────────────────────

def send_control(cmd: str) -> str:
    """Send a command to the running bt-speaker daemon via Unix socket."""
    if not SOCKET_PATH.exists():
        return "idle"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(SOCKET_PATH))
            s.sendall(cmd.encode())
            return s.recv(256).decode().strip()
    except Exception:
        return "idle"


def start_daemon(duration: float | None = None) -> None:
    """Start the bt-speaker daemon as a background process."""
    log = open("/tmp/daemon.log", "a")
    cmd = [
        "uv", "run", "main.py", "daemon",
        "--mac", SPEAKER_MAC,
        "--file", MP3_FILE,
    ]
    if duration is not None:
        cmd += ["--duration", str(duration)]
    subprocess.Popen(cmd, cwd=Path(__file__).parent, stdout=log, stderr=log)


def trigger_music(sats: int) -> None:
    """Start or restart the bt-speaker daemon for the given sat amount (1 sat = 1 second)."""
    duration = float(sats)
    print(f"Music trigger: {sats} sats → {duration}s")
    status = send_control("status")
    if status in ("playing", "paused"):
        send_control("stop")
        time.sleep(1)
    start_daemon(duration)


# ── Payment handler ───────────────────────────────────────────────────────────

def handle_payment(sats: int, source: str = "webhook") -> None:
    """
    Called whenever a new payment is confirmed.
    - Always pulses the Shelly outlet for OUTLET_PULSE_SECONDS
    - Also triggers music (1 sat = 1 second) via bt-speaker daemon
    Both run in background threads so the event loop isn't blocked.
    """
    print(f"[{source}] Payment confirmed: {sats} sats")
    threading.Thread(target=pulse_outlet, args=(OUTLET_PULSE_SECONDS,), daemon=True).start()
    threading.Thread(target=trigger_music, args=(sats,), daemon=True).start()


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def payment_webhook(request: Request):
    """Called by LNbits lnurlp when a payment is received."""
    body = await request.json()
    payment_hash = body.get("payment_hash", "")
    amount_msat = body.get("amount", 0)
    sats = max(1, int(amount_msat / 1000))

    if payment_hash and payment_hash in _seen_hashes:
        print(f"[webhook] duplicate {payment_hash[:12]}... — ignored")
        return {"status": "ok", "triggered": False, "reason": "duplicate"}

    if payment_hash:
        _seen_hashes.add(payment_hash)

    handle_payment(sats, source="webhook")
    return {"status": "ok", "triggered": True}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    result = {}

    # Shelly outlet
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"http://{SHELLY_HOST}/rpc/Switch.GetStatus?id=0")
        result["shelly"] = "on" if r.json().get("output") else "off"
    except Exception as e:
        result["shelly"] = f"unreachable ({e})"

    # LNbits
    lnbits_url = "http://localhost:5001"
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            lnbits_url = state.get("lnbits_url", lnbits_url)
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{lnbits_url}/api/v1/health")
        result["lnbits"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except Exception as e:
        result["lnbits"] = f"unreachable ({e})"

    # LND (via LNbits wallet endpoint — requires invoice key)
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{lnbits_url}/api/v1/wallet",
                    headers={"X-Api-Key": state["invoice_key"]},
                )
            if r.status_code == 200:
                balance_sats = r.json().get("balance", 0) // 1000
                result["lnd"] = f"ok (balance: {balance_sats} sats)"
            else:
                result["lnd"] = f"http {r.status_code}"
        except Exception as e:
            result["lnd"] = f"unreachable ({e})"
    else:
        result["lnd"] = "unconfigured (no state file)"

    # BT speaker daemon
    result["daemon"] = send_control("status")

    # Poller state
    result["seen_hashes"] = len(_seen_hashes)

    return result


# ── QR donation page ──────────────────────────────────────────────────────────

@app.get("/qr", response_class=HTMLResponse)
async def qr_page():
    """Fullscreen QR code donation page."""
    if not STATE_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="LNbits not configured yet. Run: uv run setup_lnbits.py",
        )

    state = json.loads(STATE_FILE.read_text())
    qr_url = state["qr_url"]
    lnurl = state["lnurl"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Donate Sats — TIMECHAIN</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #000;
      color: #f7931a;
      font-family: monospace;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      text-align: center;
      gap: 24px;
    }}
    h1 {{ font-size: 2rem; letter-spacing: 0.1em; }}
    p {{ font-size: 1rem; color: #aaa; }}
    img {{
      width: min(80vw, 400px);
      height: auto;
      border: 4px solid #f7931a;
      border-radius: 8px;
      background: white;
      padding: 8px;
    }}
    .code {{
      font-size: 0.65rem;
      color: #555;
      word-break: break-all;
      max-width: 400px;
    }}
    .pulse {{
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.5; }}
    }}
    button {{
      background: #111;
      color: #f7931a;
      border: 2px solid #f7931a;
      border-radius: 6px;
      padding: 10px 24px;
      font-family: monospace;
      font-size: 1rem;
      cursor: pointer;
      transition: background 0.2s;
    }}
    button:hover {{ background: #1a1a00; }}
    button:disabled {{ opacity: 0.4; cursor: default; }}
    .invoice-controls {{
      display: none;
      flex-direction: row;
      align-items: center;
      gap: 10px;
    }}
    .invoice-controls input {{
      background: #111;
      color: #f7931a;
      border: 2px solid #f7931a;
      border-radius: 6px;
      padding: 10px 14px;
      font-family: monospace;
      font-size: 1rem;
      width: 120px;
      text-align: center;
    }}
    .invoice-controls input:focus {{ outline: none; border-color: #ffb347; }}
    #loading {{ color: #555; font-size: 0.9rem; min-height: 1.2em; }}
  </style>
</head>
<body>
  <h1>⚡ TIMECHAIN</h1>
  <p class="pulse" id="tagline">Donate sats → trigger the outlet</p>
  <img id="qr-img" src="{qr_url}" alt="QR Code">
  <p id="scan-hint">Scan with any Lightning wallet</p>
  <div id="code-display" class="code">{lnurl}</div>
  <div id="loading"></div>

  <div class="invoice-controls" id="invoice-controls">
    <input type="number" id="sats-input" min="1" value="21" placeholder="sats">
    <button onclick="generateInvoice()">Generate Invoice</button>
  </div>

  <button id="toggle-btn" onclick="toggleMode()">Switch to Lightning Invoice</button>

  <script>
    const LNURL_QR = "{qr_url}";
    const LNURL_CODE = "{lnurl}";
    let mode = "lnurl";

    function toggleMode() {{
      if (mode === "lnurl") {{
        mode = "bolt11";
        document.getElementById("invoice-controls").style.display = "flex";
        document.getElementById("toggle-btn").textContent = "Switch to LNURL (reusable)";
        document.getElementById("scan-hint").textContent = "Enter sats and generate a Lightning invoice";
        document.getElementById("code-display").textContent = "";
        document.getElementById("qr-img").src = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
        document.getElementById("tagline").classList.remove("pulse");
        document.getElementById("tagline").textContent = "1 sat = 1 second of music";
      }} else {{
        mode = "lnurl";
        document.getElementById("invoice-controls").style.display = "none";
        document.getElementById("toggle-btn").textContent = "Switch to Lightning Invoice";
        document.getElementById("scan-hint").textContent = "Scan with any Lightning wallet";
        document.getElementById("code-display").textContent = LNURL_CODE;
        document.getElementById("qr-img").src = LNURL_QR;
        document.getElementById("tagline").classList.add("pulse");
        document.getElementById("tagline").textContent = "Donate sats → trigger the outlet";
        document.getElementById("loading").textContent = "";
      }}
    }}

    async function generateInvoice() {{
      const sats = parseInt(document.getElementById("sats-input").value);
      if (!sats || sats < 1) {{ alert("Enter a valid number of sats."); return; }}

      const loading = document.getElementById("loading");
      const btn = event.target;
      btn.disabled = true;
      loading.textContent = "Generating invoice...";

      try {{
        const resp = await fetch(`/invoice?amount=${{sats}}`);
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        document.getElementById("qr-img").src = data.qr_url;
        document.getElementById("code-display").textContent = data.bolt11;
        document.getElementById("scan-hint").textContent = `${{sats}} sat${{sats !== 1 ? "s" : ""}} — single-use invoice`;
        loading.textContent = "";
      }} catch (e) {{
        loading.textContent = "Error: " + e.message;
      }} finally {{
        btn.disabled = false;
      }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ── Invoice endpoint ──────────────────────────────────────────────────────────

@app.get("/invoice")
async def create_invoice(amount: int = 1):
    """Create a fresh bolt11 Lightning invoice for `amount` sats and return its QR URL."""
    if not STATE_FILE.exists():
        raise HTTPException(status_code=503, detail="LNbits not configured yet.")
    if amount < 1:
        raise HTTPException(status_code=400, detail="Amount must be at least 1 sat.")

    state = json.loads(STATE_FILE.read_text())
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{state['lnbits_url']}/api/v1/payments",
            headers={"X-Api-Key": state["invoice_key"]},
            json={
                "out": False,
                "amount": amount,
                "memo": f"TIMECHAIN — {amount} sats",
                "webhook": "http://127.0.0.1:8000/webhook",
            },
        )
    if resp.status_code != 201:
        raise HTTPException(status_code=502, detail=f"LNbits error: {resp.text}")

    data = resp.json()
    payment_request = data["payment_request"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={payment_request}"
    return JSONResponse({"bolt11": payment_request, "qr_url": qr_url, "amount": amount})


# ── Fallback poller ───────────────────────────────────────────────────────────

async def poll_lnbits_payments() -> None:
    """
    Polls LNbits every 5s for newly settled payments.

    Protects against the LND invoice stream dropping over Tailscale — if LNbits
    never fires the webhook, this catches the payment within ~5 seconds.

    On startup it seeds _seen_hashes with ALL existing payments (any status)
    so we never act on history — only genuinely new settlements trigger anything.
    """
    # Give LNbits a moment to start, then seed all historical hashes
    await asyncio.sleep(5)
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    f"{state.get('lnbits_url', 'http://localhost:5001')}/api/v1/payments?limit=200",
                    headers={"X-Api-Key": state["invoice_key"]},
                )
            if resp.status_code == 200:
                for p in resp.json():
                    if p.get("payment_hash"):
                        _seen_hashes.add(p["payment_hash"])
                print(f"[poller] seeded {len(_seen_hashes)} hashes — ready, watching for new payments")
            else:
                print(f"[poller] seed failed: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[poller] seed error: {e}")

    while True:
        await asyncio.sleep(5)
        if not STATE_FILE.exists():
            continue
        try:
            state = json.loads(STATE_FILE.read_text())
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{state.get('lnbits_url', 'http://localhost:5001')}/api/v1/payments?limit=10",
                    headers={"X-Api-Key": state["invoice_key"]},
                )
            if resp.status_code != 200:
                continue
            for p in resp.json():
                # Accept both success and pending incoming payments.
                # Pending = LNbits hasn't confirmed with LND yet, but Lightning
                # is instant — if it's pending and incoming it almost certainly settled.
                if p.get("status") not in ("success", "pending"):
                    continue
                if p.get("amount", 0) <= 0:  # skip outgoing
                    continue
                ph = p.get("payment_hash", "")
                if not ph or ph in _seen_hashes:
                    continue
                # New payment the webhook missed
                _seen_hashes.add(ph)
                sats = p["amount"] // 1000
                status = p.get("status")
                handle_payment(sats, source=f"poller({status})")
        except Exception as e:
            print(f"[poller] error: {e}")


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(poll_lnbits_payments())


if __name__ == "__main__":
    uvicorn.run("webhook:app", host="0.0.0.0", port=8000, reload=False)
