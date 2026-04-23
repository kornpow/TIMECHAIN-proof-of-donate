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

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

SOCKET_PATH = Path(__file__).parent / ".bt-speaker.sock"
STATE_FILE = Path(__file__).parent / ".lnbits-state.json"
MP3_FILE = "timechain-song_this-is-no-me-there-is-no-you.mp3"
SPEAKER_MAC = "90-f2-60-a7-d1-12"


def send_control(cmd: str) -> str:
    """Send a command to the running bt-speaker daemon."""
    if not SOCKET_PATH.exists():
        return "no_daemon"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(SOCKET_PATH))
        s.sendall(cmd.encode())
        return s.recv(256).decode().strip()


def start_daemon() -> None:
    """Start the bt-speaker daemon as a background process."""
    subprocess.Popen(
        [
            "uv", "run", "main.py", "daemon",
            "--mac", SPEAKER_MAC,
            "--file", MP3_FILE,
        ],
        cwd=Path(__file__).parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@app.post("/webhook")
async def payment_webhook(request: Request):
    """
    Called by LNbits when a payment is received.
    Starts music + outlet if not already playing, or restarts from the top.
    """
    body = await request.json()
    print(f"Payment received: {body}")

    status = send_control("status")

    if status in ("playing", "paused"):
        # Already running — restart from the top
        send_control("stop")
        time.sleep(1)
        start_daemon()
    elif status in ("stopped", "finished", "no_daemon"):
        start_daemon()
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
    .lnurl {{
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
  </style>
</head>
<body>
  <h1>⚡ TIMECHAIN</h1>
  <p class="pulse">Donate sats → trigger the music</p>
  <img src="{qr_url}" alt="LNURL QR Code">
  <p>Scan with any Lightning wallet</p>
  <div class="lnurl">{lnurl}</div>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run("webhook:app", host="0.0.0.0", port=8000, reload=False)
