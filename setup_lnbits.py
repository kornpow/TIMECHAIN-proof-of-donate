"""
LNbits setup script — fully configures a fresh LNbits instance via API:

  1. Logs in and retrieves a Bearer token
  2. Gets the default wallet and API keys
  3. Installs the lnurlp extension (v1.3.0, compatible with LNbits >= 1.4.0)
  4. Activates and enables the extension for the user
  5. Creates a paylink (LNURL-pay) with a webhook pointing at our receiver
  6. Saves config to .lnbits-state.json

Usage:
  uv run setup_lnbits.py

Credentials are read from 1Password via the `op` CLI:
  op://lightning-spore/LNbits-timechain/username
  op://lightning-spore/LNbits-timechain/password

Or override with env vars:
  LNBITS_USERNAME / LNBITS_PASSWORD

Notes:
  - LNbits must already be running: see README for how to start it
  - lnbits-cli superuser is used internally to get the superuser ID
  - op binary path: ~/.local/share/mise/installs/1password-cli/2.34.0/op
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

LNBITS_URL = "http://localhost:5001"
WEBHOOK_URL = "http://localhost:8000/webhook"
STATE_FILE = Path(__file__).parent / ".lnbits-state.json"
LNBITS_PKG_DIR = Path.home() / ".local/share/uv/tools/lnbits/lib/python3.13/site-packages"
OP_BIN = Path.home() / ".local/share/mise/installs/1password-cli/2.34.0/op"

LNURLP_VERSION = "1.3.0"
LNURLP_ARCHIVE = f"https://github.com/lnbits/lnurlp/archive/refs/tags/v{LNURLP_VERSION}.zip"
LNURLP_SOURCE = "https://raw.githubusercontent.com/lnbits/lnbits-extensions/main/extensions.json"


def op_read(ref: str) -> str:
    result = subprocess.run([str(OP_BIN), "read", ref], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR reading 1Password ref {ref}: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def get_credentials() -> tuple[str, str]:
    username = os.environ.get("LNBITS_USERNAME") or op_read("op://lightning-spore/LNbits-timechain/username")
    password = os.environ.get("LNBITS_PASSWORD") or op_read("op://lightning-spore/LNbits-timechain/password")
    return username, password


def login(username: str, password: str) -> str:
    print("Step 1: Logging in...")
    r = requests.post(f"{LNBITS_URL}/api/v1/auth", json={"username": username, "password": password})
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        print(f"ERROR: no access_token in response: {r.text}")
        sys.exit(1)
    print("  OK")
    return token


def get_wallet(token: str) -> tuple[str, str, str]:
    """Returns (wallet_id, admin_key, invoice_key)."""
    print("Step 2: Getting wallet...")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{LNBITS_URL}/api/v1/wallets", headers=headers)
    r.raise_for_status()
    wallet = r.json()[0]
    print(f"  Wallet: {wallet['name']} ({wallet['id']})")
    return wallet["id"], wallet["adminkey"], wallet["inkey"]


def install_extension(token: str) -> None:
    print(f"Step 3: Installing lnurlp v{LNURLP_VERSION}...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(
        f"{LNBITS_URL}/api/v1/extension",
        headers=headers,
        json={"ext_id": "lnurlp", "archive": LNURLP_ARCHIVE, "source_repo": LNURLP_SOURCE, "version": LNURLP_VERSION},
    )
    if r.status_code == 200:
        print("  Installed.")
    else:
        print(f"  WARNING: {r.status_code} {r.text}")


def activate_extension(token: str) -> None:
    print("Step 4: Activating and enabling lnurlp...")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.put(f"{LNBITS_URL}/api/v1/extension/lnurlp/activate", headers=headers)
    print(f"  activate: {r.json().get('message', r.text)}")
    r = requests.put(f"{LNBITS_URL}/api/v1/extension/lnurlp/enable", headers=headers)
    print(f"  enable:   {r.json().get('message', r.text)}")


def create_paylink(admin_key: str) -> dict:
    print("Step 5: Creating LNURL paylink...")
    r = requests.post(
        f"{LNBITS_URL}/lnurlp/api/v1/links",
        headers={"X-Api-Key": admin_key, "Content-Type": "application/json"},
        json={
            "description": "Donate sats to trigger the music!",
            "min": 1,
            "max": 1000000,
            "comment_chars": 100,
            "webhook_url": WEBHOOK_URL,
            "success_text": "Thanks! Enjoy the music!",
            "disposable": False,
        },
    )
    if r.status_code in (200, 201):
        link = r.json()
        print(f"  Paylink ID: {link['id']}")
        return link
    print(f"ERROR creating paylink: {r.status_code} {r.text}")
    sys.exit(1)


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(f"\nState saved to {STATE_FILE}")


def main() -> None:
    username, password = get_credentials()

    token = login(username, password)
    wallet_id, admin_key, invoice_key = get_wallet(token)
    install_extension(token)
    activate_extension(token)
    paylink = create_paylink(admin_key)

    qr_url = f"{LNBITS_URL}/api/v1/qrcode/{paylink['lnurl']}"

    state = {
        "lnbits_url": LNBITS_URL,
        "webhook_url": WEBHOOK_URL,
        "wallet_id": wallet_id,
        "admin_key": admin_key,
        "invoice_key": invoice_key,
        "paylink_id": paylink["id"],
        "lnurl": paylink["lnurl"],
        "qr_url": qr_url,
    }

    save_state(state)

    print("\n--- Setup complete ---")
    print(f"  LNbits UI:  {LNBITS_URL}")
    print(f"  LNURL:      {paylink['lnurl']}")
    print(f"  QR code:    {qr_url}")
    print(f"  Webhook:    {WEBHOOK_URL}")


if __name__ == "__main__":
    main()
