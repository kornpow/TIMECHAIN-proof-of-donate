"""
Bluetooth Speaker + MP3 Playback (macOS + Linux)

Two modes:
  daemon  — start the player in the background, listens on a Unix socket
  control — send commands to the running daemon (play, pause, resume, stop, status)

Requirements:
  macOS: brew install blueutil
  Linux: sudo apt install bluez pulseaudio

Usage:
  uv run main.py daemon --mac AA:BB:CC:DD:EE:FF --file music.mp3
  uv run main.py control pause
  uv run main.py control resume
  uv run main.py control stop
  uv run main.py control status
"""

import argparse
import platform
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pygame
from ishelly.client import ShellyPlug
from ishelly.components.switch import SwitchSetParams


SYSTEM = platform.system()
SOCKET_PATH = Path(__file__).parent / ".bt-speaker.sock"
SHELLY_HOST = "192.168.6.90"


# ── Bluetooth ─────────────────────────────────────────────────────────────────

def list_devices() -> None:
    if SYSTEM == "Darwin":
        result = subprocess.run(["blueutil", "--paired"], capture_output=True, text=True)
        print(result.stdout)
    else:
        subprocess.run(["bluetoothctl", "devices"])


def connect_speaker(mac: str, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        print(f"Connecting to {mac} (attempt {attempt}/{retries})...")
        if SYSTEM == "Darwin":
            try:
                subprocess.run(["blueutil", "--version"], capture_output=True, check=True)
            except FileNotFoundError:
                print("ERROR: blueutil not found. Install: brew install blueutil")
                sys.exit(1)
            # Check if already connected first
            chk = subprocess.run(["blueutil", "--is-connected", mac], capture_output=True, text=True)
            if chk.stdout.strip() == "1":
                print("Already connected.")
                time.sleep(1)
                return True
            try:
                result = subprocess.run(
                    ["blueutil", "--connect", mac],
                    capture_output=True, text=True, timeout=15
                )
            except subprocess.TimeoutExpired:
                print(f"  Timed out connecting to {mac}")
                continue
        else:
            result = subprocess.run(
                ["bluetoothctl", "connect", mac], capture_output=True, text=True
            )

        if result.returncode == 0:
            print("Connected. Waiting for audio routing...")
            time.sleep(3)
            return True
        print(f"  Failed: {result.stderr.strip()}")
        time.sleep(2)

    print("ERROR: Could not connect after all retries.")
    return False


def set_audio_output(device_name: str) -> None:
    try:
        subprocess.run(["SwitchAudioSource", "-s", device_name], capture_output=True, check=True)
        print(f"Audio output switched to: {device_name}")
    except FileNotFoundError:
        pass
    except subprocess.CalledProcessError as e:
        print(f"Warning: could not switch audio output: {e}")


# ── Player daemon ─────────────────────────────────────────────────────────────

class Player:
    def __init__(self, path: str, volume: float):
        self.path = path
        self.volume = volume
        self.state = "stopped"  # playing | paused | stopped | finished
        self.shelly = ShellyPlug(SHELLY_HOST)

    def _outlet(self, on: bool) -> None:
        try:
            self.shelly.switch.set(SwitchSetParams(id=0, on=on))
            print(f"Outlet {'on' if on else 'off'}.")
        except Exception as e:
            print(f"Warning: could not set outlet: {e}")

    def start(self) -> None:
        pygame.mixer.init()
        pygame.mixer.music.load(self.path)
        pygame.mixer.music.set_volume(max(0.0, min(1.0, self.volume)))
        pygame.mixer.music.play()
        self.state = "playing"
        self._outlet(True)
        print(f"Playing: {self.path}")

    def pause(self) -> str:
        if self.state == "playing":
            pygame.mixer.music.pause()
            self.state = "paused"
            return "paused"
        return f"cannot pause: state is {self.state}"

    def resume(self) -> str:
        if self.state == "paused":
            pygame.mixer.music.unpause()
            self.state = "playing"
            return "resumed"
        return f"cannot resume: state is {self.state}"

    def stop(self) -> str:
        pygame.mixer.music.stop()
        self.state = "stopped"
        self._outlet(False)
        return "stopped"

    def status(self) -> str:
        if self.state == "playing" and not pygame.mixer.music.get_busy():
            self.state = "finished"
        return self.state

    def tick(self) -> None:
        """Update finished state if playback ended naturally."""
        if self.state == "playing" and not pygame.mixer.music.get_busy():
            self.state = "finished"
            self._outlet(False)


def handle_client(conn: socket.socket, player: Player, stop_event: threading.Event) -> None:
    with conn:
        try:
            cmd = conn.recv(64).decode().strip().lower()
            if cmd == "pause":
                reply = player.pause()
            elif cmd == "resume":
                reply = player.resume()
            elif cmd == "stop":
                reply = player.stop()
                stop_event.set()
            elif cmd == "status":
                reply = player.status()
            else:
                reply = f"unknown command: {cmd}"
            conn.sendall((reply + "\n").encode())
        except Exception as e:
            conn.sendall(f"error: {e}\n".encode())


def run_daemon(path: str, volume: float, mac: str | None, audio_device: str | None, no_connect: bool) -> None:
    if not no_connect:
        if not mac:
            print("ERROR: --mac required")
            sys.exit(1)
        if not connect_speaker(mac):
            sys.exit(1)

    if audio_device:
        set_audio_output(audio_device)

    player = Player(path, volume)
    player.start()

    # Clean up stale socket
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    stop_event = threading.Event()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(5)
    server.settimeout(0.5)

    print(f"Daemon listening on {SOCKET_PATH}")
    print("Control with: uv run main.py control [pause|resume|stop|status]")

    try:
        while not stop_event.is_set():
            player.tick()
            if player.state == "finished":
                print("Playback finished.")
                break
            try:
                conn, _ = server.accept()
                t = threading.Thread(target=handle_client, args=(conn, player, stop_event), daemon=True)
                t.start()
            except TimeoutError:
                continue
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        server.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        pygame.mixer.quit()
        print("Daemon stopped.")


# ── Control client ────────────────────────────────────────────────────────────

def run_control(cmd: str) -> None:
    if not SOCKET_PATH.exists():
        print("ERROR: No daemon running. Start with: uv run main.py daemon --file music.mp3 --mac ...")
        sys.exit(1)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(SOCKET_PATH))
        s.sendall(cmd.encode())
        reply = s.recv(256).decode().strip()
        print(reply)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Bluetooth speaker MP3 player")
    sub = parser.add_subparsers(dest="mode", required=True)

    # daemon
    d = sub.add_parser("daemon", help="Start the player daemon")
    d.add_argument("--mac", help="Bluetooth speaker MAC address")
    d.add_argument("--file", required=True, help="Path to MP3 file")
    d.add_argument("--volume", type=float, default=0.8, help="Volume 0.0–1.0 (default: 0.8)")
    d.add_argument("--audio-device", default=None, help="(macOS) audio output device name")
    d.add_argument("--no-connect", action="store_true", help="Skip Bluetooth connection")
    d.add_argument("--list-devices", action="store_true", help="List paired devices and exit")

    # control
    c = sub.add_parser("control", help="Send a command to the running daemon")
    c.add_argument("cmd", choices=["pause", "resume", "stop", "status"])

    args = parser.parse_args()

    if args.mode == "daemon":
        if args.list_devices:
            list_devices()
            sys.exit(0)
        run_daemon(
            path=args.file,
            volume=args.volume,
            mac=args.mac,
            audio_device=args.audio_device,
            no_connect=args.no_connect,
        )
    elif args.mode == "control":
        run_control(args.cmd)


if __name__ == "__main__":
    main()
