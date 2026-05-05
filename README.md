# TIMECHAIN — Proof of Donate

Donate sats over Lightning → music plays on a Bluetooth speaker → Shelly outlet turns on.

**Rate: 1 sat = 1 second of music.**

Built with Python, LNbits, pygame, blueutil, and ishelly.

---

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Copy env file (FakeWallet is default — no real Lightning node needed)
cp .env.example .env

# 3. Start the full stack (LNbits + webhook server)
./start.sh

# 4. First run only: configure LNbits (creates wallet, LNURL, paylink, webhook)
uv run setup_lnbits.py

# 5. Open the QR donation page
open http://localhost:8000/qr        # macOS
xdg-open http://localhost:8000/qr   # Linux
```

That's it. Stack is up. Donors scan the QR code, sats flow, music plays.

---

## Sending Test Payments

You don't need a real Lightning wallet to test. The webhook server accepts plain HTTP POSTs, so you can simulate any payment amount with curl:

```bash
# Simulate a 10-sat payment (10 seconds of music)
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"amount": 10000}'

# Simulate a 21-sat payment (21 seconds of music)
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"amount": 21000}'

# Simulate a 60-sat payment (1 minute of music)
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"amount": 60000}'
```

Amount is in millisatoshis (msat). Formula: sats × 1000 = msat.

Or use the included helper script:

```bash
./test_payment.sh 21     # send 21 sats
./test_payment.sh 100    # send 100 sats
```

To test without Bluetooth (no speaker) and without the Shelly outlet, start the daemon manually with --no-connect and --no-outlet:

```bash
uv run main.py daemon \
  --file timechain-song_this-is-no-me-there-is-no-you.mp3 \
  --no-connect \
  --no-outlet \
  --duration 30
```

Then in another terminal, simulate a payment. Music plays through your default audio output.

---

## start.sh Commands

```
./start.sh                     start LNbits + webhook server (default)
./start.sh stop                stop everything
./start.sh status              show running status and health checks
./start.sh logs                tail all logs in real time (Ctrl-C to exit)
./start.sh play [seconds]      play the song locally (default: full song)
./start.sh outlet [seconds]    toggle Shelly outlet on for N seconds (default: 5)
./start.sh help                show help
```

Examples:

```bash
./start.sh play 30       # play 30 seconds of music
./start.sh outlet        # toggle outlet on for 5 seconds
./start.sh outlet 10     # toggle outlet on for 10 seconds
./start.sh status        # show what's running + health check
./start.sh logs          # tail /tmp/lnbits.log + /tmp/webhook.log + /tmp/daemon.log
```

---

## Endpoints

| URL | Description |
|---|---|
| `http://localhost:5001` | LNbits wallet UI |
| `http://localhost:8000/qr` | Fullscreen QR donation page — shows LNURL by default, toggle to bolt11 invoice |
| `http://localhost:8000/invoice?amount=21` | GET — generates a fresh single-use bolt11 invoice for 21 sats |
| `http://localhost:8000/health` | Playback status — returns `{"daemon": "playing" | "paused" | "idle"}` |
| `http://localhost:8000/webhook` | LNbits payment webhook (POST, body: `{"amount": <msat>}`) |

---

## How It Works

1. **LNbits** runs a local Lightning wallet with a LNURL paylink
2. A donor scans the QR code and sends sats
3. LNbits fires a **webhook** to our FastAPI server (`/webhook`)
4. The webhook starts the **bt-speaker daemon**, playing the MP3 over Bluetooth for exactly as many seconds as sats paid
5. The **Shelly Plus Plug US** outlet turns on for the duration of playback, then turns off

---

## Setup Details

### Requirements

**macOS:**
```bash
brew install blueutil
brew install switchaudio-osx   # optional, for auto audio routing
```

**Linux:**
```bash
sudo apt install bluez pulseaudio   # or pipewire-pulse
```

**1Password CLI** (for credentials — optional, can use env vars instead):
```bash
mise install 1password-cli
```

Secret references used:
- `op://lightning-spore/LNbits-timechain/username`
- `op://lightning-spore/LNbits-timechain/password`

Override with env vars if you don't use 1Password:
```bash
LNBITS_USERNAME=admin LNBITS_PASSWORD=yourpass uv run setup_lnbits.py
```

### Wallet Backends

The default `.env` uses **FakeWallet** — no real Lightning node required, perfect for development and testing.

For a real Lightning node, update `.env`:
```
LNBITS_BACKEND_WALLET_CLASS=LndRestWallet
LND_REST_ENDPOINT=https://127.0.0.1:8080
LND_REST_CERT=/path/to/tls.cert
LND_REST_MACAROON=/path/to/admin.macaroon
```

---

## main.py Daemon Commands

```bash
# Start the Bluetooth + playback daemon
uv run main.py daemon --mac AA:BB:CC:DD:EE:FF --file song.mp3

# With duration limit
uv run main.py daemon --mac AA:BB:CC:DD:EE:FF --file song.mp3 --duration 30

# Skip Bluetooth (use system audio output) and skip outlet
uv run main.py daemon --file song.mp3 --no-connect --no-outlet

# Control a running daemon
uv run main.py control pause
uv run main.py control resume
uv run main.py control stop
uv run main.py control status   # returns: playing | paused | idle

# List paired Bluetooth devices
uv run main.py daemon --list-devices
```

---

## Hardware

| Device | Config |
|---|---|
| Bluetooth speaker | JBL Go 4 — MAC `90-f2-60-a7-d1-12` |
| Smart outlet | Shelly Plus Plug US — `172.20.10.2` |

To change these, edit `webhook.py` (`SPEAKER_MAC`) and `main.py` (`SHELLY_HOST`).

---

## Logs

| File | Contents |
|---|---|
| `/tmp/lnbits.log` | LNbits server output |
| `/tmp/webhook.log` | Webhook server output |
| `/tmp/daemon.log` | bt-speaker daemon output (Bluetooth connect, playback, outlet) |

Tail them all at once: `./start.sh logs`

---

## Scan for Bluetooth Devices

```bash
blueutil --inquiry 10   # scan for unpaired devices (10 seconds)
blueutil --paired       # list already-paired devices
```

---

## Notes

- The Unix socket lives at `.bt-speaker.sock` in the project directory (gitignored)
- LNbits state (wallet keys, LNURL, paylink ID) saved to `.lnbits-state.json` (gitignored)
- macOS port 5000 is taken by Control Center — LNbits runs on **5001**
- **Linux**: audio routes via PulseAudio/PipeWire automatically once speaker is connected
- **macOS**: if audio doesn't route automatically, pass `--audio-device "Your Speaker Name"` to the daemon
- `blueutil --connect` has a 15-second timeout per attempt; if the speaker is already connected it skips straight to playback



## LND Creds

```
lncli bakemacaroon \
  invoices:read invoices:write \
  info:read \
  offchain:read offchain:write
```