# bt-speaker

Play an MP3 through a Bluetooth speaker from the command line.

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

**Find your speaker's MAC address**
```bash
# macOS
uv run main.py --list-devices

# Linux
bluetoothctl devices
```

Pair the speaker in your OS Bluetooth settings first, then:

```bash
uv run main.py --mac AA:BB:CC:DD:EE:FF --file song.mp3
```

**Options**

| Flag | Description | Default |
|---|---|---|
| `--mac` | Bluetooth speaker MAC address | required |
| `--file` | Path to MP3 file | required |
| `--volume` | Volume 0.0–1.0 | `0.8` |
| `--audio-device` | macOS output device name (optional) | — |
| `--list-devices` | List paired Bluetooth devices and exit | — |

## Notes

- **Linux**: connection uses `bluetoothctl`, audio routes via PulseAudio/PipeWire automatically once connected.
- **macOS**: if audio doesn't route automatically, pass `--audio-device "Your Speaker Name"` (requires `switchaudio-osx`).
