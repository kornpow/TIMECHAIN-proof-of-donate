# TIMECHAIN — Proof of Donate

Donate sats over Lightning → music plays on a Bluetooth speaker → Shelly outlet turns on.

**Rate: 1 sat = 1 second of music.**

Built with Python, LNbits, pygame, blueutil, and ishelly.

---

## How it works

1. **LNbits** runs a local Lightning wallet with a LNURL paylink
2. A donor scans the QR code and sends sats
3. LNbits fires a **webhook** to our FastAPI server
4. The webhook starts the **bt-speaker daemon**, playing the MP3 over Bluetooth for exactly as many seconds as sats paid
5. The **Shelly Plus Plug US** outlet turns on for the duration of playback, then turns off

---

## Requirements

**macOS**
```bash
brew install blueutil
brew install switchaudio-osx  # optional, for auto audio routing
```

**Linux**
```bash
sudo apt install bluez pulseaudio  # or pipewire-pulse
```

**1Password CLI** (for credentials)
```bash
mise install 1password-cli
```
Secret references used:
- `op://lightning-spore/LNbits-timechain/username`
- `op://lightning-spore/LNbits-timechain/password`

---

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Copy and configure environment
cp .env.example .env

# 3. Start LNbits (must run from its package dir due to static file paths)
cd ~/.local/share/uv/tools/lnbits/lib/python3.13/site-packages
cp /path/to/timechain_project/.env .
nohup uv tool run lnbits > /tmp/lnbits.log 2>&1 &

# 4. Start the webhook server
cd /path/to/timechain_project
nohup uv run webhook.py > /tmp/webhook.log 2>&1 &

# 5. Run the one-time LNbits setup (installs lnurlp, creates paylink + webhook)
uv run setup_lnbits.py
```

Config is saved to `.lnbits-state.json` (gitignored — contains API keys).

---

## Running

**Start the Bluetooth + Shelly daemon manually:**
```bash
uv run main.py daemon --mac AA:BB:CC:DD:EE:FF --file song.mp3

# Optional: limit playback to N seconds
uv run main.py daemon --mac AA:BB:CC:DD:EE:FF --file song.mp3 --duration 30
```

**Control playback:**
```bash
uv run main.py control pause
uv run main.py control resume
uv run main.py control stop
uv run main.py control status   # returns: playing | paused | idle
```

**Scan for nearby Bluetooth devices:**
```bash
blueutil --inquiry 10   # scan unpaired
blueutil --paired       # list paired
```

---

## Endpoints

| URL | Description |
|---|---|
| `http://localhost:5001` | LNbits wallet UI |
| `http://localhost:8000/qr` | Fullscreen QR donation page — shows LNURL by default, toggle to bolt11 invoice |
| `http://localhost:8000/invoice` | `GET` — generates a fresh single-use bolt11 invoice (used by the QR toggle) |
| `http://localhost:8000/health` | Playback status — returns `{"daemon": "playing" \| "paused" \| "idle"}` |
| `http://localhost:8000/webhook` | LNbits payment webhook (POST) |

---

## Hardware

| Device | Config |
|---|---|
| Bluetooth speaker | JBL Go 4 — MAC `90-f2-60-a7-d1-12` |
| Smart outlet | Shelly Plus Plug US — `192.168.6.90` |

To change these, edit `webhook.py` (`SPEAKER_MAC`) and `main.py` (`SHELLY_HOST`).

---

## Logs

| File | Contents |
|---|---|
| `/tmp/lnbits.log` | LNbits server output |
| `/tmp/webhook.log` | Webhook server output |
| `/tmp/daemon.log` | bt-speaker daemon output (Bluetooth connect, playback, outlet) |

---

## Notes

- The Unix socket lives at `.bt-speaker.sock` in the project directory (gitignored)
- LNbits state (wallet keys, LNURL, paylink ID) saved to `.lnbits-state.json` (gitignored)
- macOS port 5000 is taken by Control Center — LNbits runs on **5001**
- **Linux**: audio routes via PulseAudio/PipeWire automatically once speaker is connected
- **macOS**: if audio doesn't route automatically, pass `--audio-device "Your Speaker Name"` to the daemon
- `blueutil --connect` has a 15-second timeout per attempt; if the speaker is already connected it skips straight to playback

