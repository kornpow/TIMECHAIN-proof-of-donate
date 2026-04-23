"""
Webhook receiver for LNbits payment events.

LNbits fires a POST to /webhook when a payment is received.
This triggers the bt-speaker daemon to play music and turns on the Shelly outlet.

Run: uv run webhook.py
"""

import socket
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
import uvicorn

app = FastAPI()

SOCKET_PATH = Path(__file__).parent / ".bt-speaker.sock"
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
        import time; __import__('time').sleep(1)
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


if __name__ == "__main__":
    uvicorn.run("webhook:app", host="0.0.0.0", port=8000, reload=False)
