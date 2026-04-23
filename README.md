# bt-speaker

Play an MP3 through a Bluetooth speaker with synchronized Shelly outlet control.

## What it does

- Connects to a paired Bluetooth speaker via `blueutil` (macOS) or `bluetoothctl` (Linux)
- Plays an MP3 using `pygame`
- Turns a **Shelly Plus Plug US** outlet on/off in sync with playback
- Runs as a background daemon controlled via a Unix socket (`.bt-speaker.sock` in the project dir)

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

## Setup

```bash
uv sync
```

## Usage

**Scan for / list paired devices**
```bash
# macOS
blueutil --inquiry 10       # scan for nearby unpaired devices
blueutil --paired           # list already paired devices

# Linux
bluetoothctl devices
```

Pair the speaker in your OS Bluetooth settings first, then:

**Start the daemon**
```bash
uv run main.py daemon --mac AA:BB:CC:DD:EE:FF --file song.mp3
```

**Control playback** (from another terminal or programmatically)
```bash
uv run main.py control pause
uv run main.py control resume
uv run main.py control stop
uv run main.py control status
```

**Options**

| Flag | Description | Default |
|---|---|---|
| `--mac` | Bluetooth speaker MAC address | required |
| `--file` | Path to MP3 file | required |
| `--volume` | Volume 0.0–1.0 | `0.8` |
| `--no-connect` | Skip Bluetooth connection step | — |
| `--audio-device` | macOS output device name (requires `switchaudio-osx`) | — |
| `--list-devices` | List paired Bluetooth devices and exit | — |

## Shelly outlet

The Shelly Plus Plug US at `192.168.6.90` is turned **on** when music starts and **off** when it stops or finishes. Configure the IP in `main.py`:

```python
SHELLY_HOST = "192.168.6.90"
```

## Notes

- The Unix socket lives at `.bt-speaker.sock` in the project directory and is cleaned up on daemon exit.
- **Linux**: audio routes via PulseAudio/PipeWire automatically once the speaker is connected.
- **macOS**: if audio doesn't route automatically, pass `--audio-device "Your Speaker Name"`.
