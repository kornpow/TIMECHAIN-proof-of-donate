#!/usr/bin/env python3
"""
make_invoice.py — create a bolt11 invoice from the LNURL paylink.

Usage:
    uv run make_invoice.py [sats]

Examples:
    uv run make_invoice.py        # defaults to 21 sats
    uv run make_invoice.py 100    # 100 sats

Prints the bolt11 payment request and a QR code URL you can open in a browser.
"""

import json
import sys
from pathlib import Path

import httpx

STATE_FILE = Path(__file__).parent / ".lnbits-state.json"


def decode_lnurl(lnurl: str) -> str:
    """Bech32-decode an LNURL to its underlying https URL."""
    import bech32
    hrp, data = bech32.bech32_decode(lnurl.lower())
    if data is None:
        raise ValueError(f"Invalid LNURL: {lnurl}")
    decoded_bytes = bytes(bech32.convertbits(data, 5, 8, False))
    return decoded_bytes.decode("utf-8")


def make_invoice(sats: int) -> dict:
    state = json.loads(STATE_FILE.read_text())
    lnurl = state["lnurl"]

    # Step 1: decode LNURL → callback URL
    callback_url = decode_lnurl(lnurl)
    print(f"LNURL callback: {callback_url}")

    # Step 2: fetch the paylink metadata (min/max, callback)
    with httpx.Client(timeout=10) as client:
        meta_resp = client.get(callback_url)
    meta_resp.raise_for_status()
    meta = meta_resp.json()

    if meta.get("status") == "ERROR":
        raise RuntimeError(f"LNURL error: {meta.get('reason')}")

    callback = meta["callback"]
    min_sats = meta["minSendable"] // 1000
    max_sats = meta["maxSendable"] // 1000
    print(f"Range: {min_sats}–{max_sats} sats")

    if not (min_sats <= sats <= max_sats):
        raise ValueError(f"{sats} sats is outside allowed range {min_sats}–{max_sats}")

    # Step 3: request the invoice for the given amount
    amount_msat = sats * 1000
    with httpx.Client(timeout=10) as client:
        inv_resp = client.get(callback, params={"amount": amount_msat})
    inv_resp.raise_for_status()
    inv = inv_resp.json()

    if inv.get("status") == "ERROR":
        raise RuntimeError(f"Invoice error: {inv.get('reason')}")

    bolt11 = inv["pr"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={bolt11}"

    return {"bolt11": bolt11, "qr_url": qr_url, "sats": sats}


def main():
    sats = int(sys.argv[1]) if len(sys.argv) > 1 else 21

    print(f"\nRequesting invoice for {sats} sats...\n")
    result = make_invoice(sats)

    print(f"bolt11:  {result['bolt11']}")
    print(f"QR URL:  {result['qr_url']}")
    print(f"\nOpen the QR URL in your browser to scan, or paste the bolt11 into any Lightning wallet.")


if __name__ == "__main__":
    main()
