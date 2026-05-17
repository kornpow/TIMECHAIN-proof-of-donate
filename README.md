# TIMECHAIN — Proof of Donate

Donate sats over Lightning → a cuckoo clock chimes + music plays on a Bluetooth speaker.

**Rate: 1 sat = 1 second of music.**

Built with Python, LNbits, pygame, blueutil, and ishelly.

---

## Demo

> **[Demo video coming soon]** — see [`media/`](media/) to contribute one.

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

That's it. Stack is up. Donors scan the QR code, sats flow, the clock chimes, music plays.

---

## How It Works

1. **LNbits** runs a local Lightning wallet with a LNURL paylink
2. A donor scans the QR code and sends sats
3. LNbits fires a **webhook** to our FastAPI server (`/webhook`)
4. The webhook starts the **bt-speaker daemon**, playing the MP3 over Bluetooth
   for exactly as many seconds as sats paid
5. The **Shelly Plus Plug US** outlet turns on for the duration of playback, then turns off
6. The Shelly powers a **12V electromagnet** mounted inside the cuckoo clock —
   the magnet pulls the chime gear, triggering the full cuckoo chime cycle

---

## The Clock

A standard cuckoo clock is modified with an externally-mounted electromagnet.
When the Shelly outlet turns on, the electromagnet pulls on the clock's chime
gear, triggering the cuckoo to come out and cycle — exactly as if the clock had
struck the hour naturally.

**The clock mechanism is not permanently modified.** The electromagnet mounts
against the existing gear with no drilling or gluing. The clock still keeps time
and chimes normally on its own schedule.

See [`hardware/README.md`](hardware/README.md) for the full modification guide,
wiring diagram, and parts list.

---

## Full Recreation Guide

Follow these steps in order to go from scratch to a fully operational installation.

### Step 1 — Assemble the hardware

Buy the parts, mount the electromagnet, wire it to the Shelly outlet.

→ [`hardware/README.md`](hardware/README.md)

### Step 2 — Generate minimal LND credentials

Bake a restricted macaroon. Never use `admin.macaroon` in production.

→ [`docs/lnd-credentials.md`](docs/lnd-credentials.md)

### Step 3 — Set up Tailscale

Join both your LND node and the deployment server to the same tailnet so LNbits
can reach LND privately.

→ [`docs/tailscale.md`](docs/tailscale.md)

### Step 4 — Set up the Cloudflare tunnel

LNURL payments require a public HTTPS domain. The Cloudflare tunnel exposes
LNbits without opening any firewall ports.

→ [`docs/cloudflare-tunnel.md`](docs/cloudflare-tunnel.md)

### Step 5 — Configure .env

```bash
cp ansible/env.example .env
# Fill in: LND_REST_ENDPOINT, LND_REST_MACAROON, LNBITS_PUBLIC_URL
```

### Step 6 — Deploy with Ansible

Installs LNbits, the webhook server, Tailscale, and the Cloudflare tunnel as
systemd services on a Debian server (e.g. Raspberry Pi).

```bash
brew install ansible
ansible-galaxy collection install community.general
export TAILSCALE_AUTH_KEY=tskey-auth-...
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

### Step 7 — Initialize LNbits

First run only — creates the wallet, LNURL paylink, and webhook registration:

```bash
uv run setup_lnbits.py
```

### Step 8 — Test

```bash
./test_payment.sh 21   # simulate a 21-sat payment
```

The clock should chime and music should play for 21 seconds.

---

## Sending Test Payments

You don't need a real Lightning wallet to test. Simulate any payment amount with curl:

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

To test without Bluetooth (no speaker) and without the Shelly outlet:

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
./start.sh outlet        # toggle outlet on for 5 seconds (triggers clock chime)
./start.sh outlet 2      # toggle outlet on for 2 seconds
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
| `http://localhost:8000/health` | Playback status — returns `{"daemon": "playing" \| "paused" \| "idle"}` |
| `http://localhost:8000/webhook` | LNbits payment webhook (POST, body: `{"amount": <msat>}`) |

---

## Hardware

| Device | Details |
|---|---|
| Cuckoo clock | Any standard cuckoo clock — see [`hardware/README.md`](hardware/README.md) |
| Electromagnet | [Baomain BM-0530B](https://www.amazon.com/dp/B01K41EZAU?th=1) — DC 12V, 950mA, 5N, 10mm stroke, ~$8 |
| 12V ~2A power supply | Barrel jack (5.5mm × 2.1mm), center positive |
| Bluetooth speaker | JBL Go 4 — MAC `90-f2-60-a7-d1-12` |
| Smart outlet | Shelly Plus Plug US — `172.16.4.55` |

To change the speaker MAC or Shelly IP, edit `webhook.py` (`SPEAKER_MAC`) and
`main.py` (`SHELLY_HOST`).

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

The default `.env` uses **FakeWallet** — no real Lightning node required, perfect
for development and testing.

For a real Lightning node, update `.env`:
```
LNBITS_BACKEND_WALLET_CLASS=LndRestWallet
LND_REST_ENDPOINT=https://100.x.x.x:8080   # Tailscale IP of your LND node
LND_REST_MACAROON=<hex-encoded baked macaroon>
LND_REST_CERT=                              # managed by Ansible — leave blank
```

See [`docs/lnd-credentials.md`](docs/lnd-credentials.md) for how to bake the
macaroon and [`docs/tailscale.md`](docs/tailscale.md) for reaching your node.

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

---

## LND Credentials

Generate a minimal macaroon — never use `admin.macaroon` in production:

```bash
lncli bakemacaroon \
  invoices:read invoices:write \
  info:read \
  offchain:read offchain:write
```

See [`docs/lnd-credentials.md`](docs/lnd-credentials.md) for the full guide
including hex export, TLS cert setup, and `.env` configuration.
