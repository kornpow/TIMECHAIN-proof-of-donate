"""
Webhook receiver for LNbits payment events.

LNbits fires a POST to /webhook when a payment is received.
This triggers the bt-speaker daemon to play music and turns on the Shelly outlet.

Endpoints:
  POST /webhook   — called by LNbits on payment received
  GET  /health    — returns current daemon playback status
  GET  /qr        — displays a fullscreen HTML QR code page for donations

Run: uv run webhook.py
"""

import json
import socket
import subprocess
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

app = FastAPI()

SOCKET_PATH = Path(__file__).parent / ".bt-speaker.sock"
STATE_FILE = Path(__file__).parent / ".lnbits-state.json"
MP3_FILE = "timechain-song_this-is-no-me-there-is-no-you.mp3"
SPEAKER_MAC = "90-f2-60-a7-d1-12"


def send_control(cmd: str) -> str:
    """Send a command to the running bt-speaker daemon."""
    if not SOCKET_PATH.exists():
        return "idle"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(SOCKET_PATH))
        s.sendall(cmd.encode())
        return s.recv(256).decode().strip()


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


@app.post("/webhook")
async def payment_webhook(request: Request):
    """
    Called by LNbits when a payment is received.
    Starts music + outlet if not already playing, or restarts from the top.
    """
    body = await request.json()
    amount_msat = body.get("amount", 0)
    sats = max(1, int(amount_msat / 1000))
    duration = float(sats)  # 1 second per sat
    print(f"Payment received: {sats} sats → {duration}s of music")

    status = send_control("status")

    if status in ("playing", "paused"):
        # Already running — restart with new duration
        send_control("stop")
        time.sleep(1)
        start_daemon(duration)
    elif status in ("idle", "stopped", "finished"):
        start_daemon(duration)
    else:
        raise HTTPException(status_code=500, detail=f"Unexpected daemon status: {status}")

    return {"status": "ok", "triggered": True}


@app.get("/health")
async def health():
    status = send_control("status")
    return {"daemon": status}


@app.get("/qr", response_class=HTMLResponse)
async def qr_page():
    """Fullscreen QR code donation page — open on any display screen."""
    if not STATE_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="LNbits not configured yet. Run: uv run setup_lnbits.py",
        )

    state = json.loads(STATE_FILE.read_text())
    qr_url = state["qr_url"]
    lnurl = state["lnurl"]
    lnbits_url = state["lnbits_url"]

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
  <p class="pulse" id="tagline">Donate sats → trigger the music</p>
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
        document.getElementById("qr-img").src = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"; // blank
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
        document.getElementById("tagline").textContent = "Donate sats → trigger the music";
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


@app.get("/invoice")
async def create_invoice(amount: int = 1):
    """Create a fresh bolt11 Lightning invoice for `amount` sats and return its QR URL."""
    if not STATE_FILE.exists():
        raise HTTPException(status_code=503, detail="LNbits not configured yet.")
    if amount < 1:
        raise HTTPException(status_code=400, detail="Amount must be at least 1 sat.")

    state = json.loads(STATE_FILE.read_text())
    invoice_key = state["invoice_key"]
    lnbits_url = state["lnbits_url"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{lnbits_url}/api/v1/payments",
            headers={"X-Api-Key": invoice_key},
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


if __name__ == "__main__":
    uvicorn.run("webhook:app", host="0.0.0.0", port=8000, reload=False)
