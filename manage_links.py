#!/usr/bin/env python3
"""
manage_links.py — manage TIMECHAIN LNURL paylinks.

Usage:
    uv run manage_links.py list
    uv run manage_links.py show <slot>
    uv run manage_links.py update <slot> [--description "..."] [--min <sats>] [--max <sats>] [--username <name>] [--webhook <url>]
    uv run manage_links.py enable <slot>
    uv run manage_links.py disable <slot>
    uv run manage_links.py qr <slot>       — print QR URL to open in browser

Examples:
    uv run manage_links.py list
    uv run manage_links.py update 3 --description "VIP Table" --min 100 --max 100
    uv run manage_links.py disable 5
    uv run manage_links.py enable 5
    uv run manage_links.py qr 3
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

STATE_FILE = Path(__file__).parent / ".lnbits-state.json"
PAYLINKS_FILE = Path(__file__).parent / ".lnbits-paylinks.json"


def load_state():
    return json.loads(STATE_FILE.read_text())


def load_links():
    return json.loads(PAYLINKS_FILE.read_text())


def get_slot(links: list, slot: int) -> dict:
    for l in links:
        if l["slot"] == slot:
            return l
    print(f"Error: slot {slot} not found (valid: 1–{len(links)})")
    sys.exit(1)


def api_get(state: dict, path: str) -> dict:
    url = f"{state['lnbits_url']}{path}"
    r = httpx.get(url, headers={"X-Api-Key": state["admin_key"]}, timeout=10)
    r.raise_for_status()
    return r.json()


def api_put(state: dict, path: str, payload: dict) -> dict:
    url = f"{state['lnbits_url']}{path}"
    r = httpx.put(url, headers={"X-Api-Key": state["admin_key"]}, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def cmd_list(args):
    state = load_state()
    links = load_links()

    # Fetch live data from LNbits
    live = {l["id"]: l for l in api_get(state, "/lnurlp/api/v1/links")}

    print(f"\n{'SLOT':>4}  {'ID':>8}  {'DESCRIPTION':<20}  {'MIN':>8}  {'MAX':>10}  {'STATUS':<8}  LIGHTNING ADDRESS")
    print("-" * 100)
    for l in links:
        lid = l["id"]
        ll = live.get(lid, {})
        enabled = "enabled" if not ll.get("is_unique") else "disabled"
        # LNbits uses `is_unique` oddly — check via `served_meta` or just show from local
        desc = ll.get("description") or l["description"]
        min_s = int(ll.get("min", l.get("min_sats", 1)))
        max_s = int(ll.get("max", l.get("max_sats", 1000000)))
        print(f"{l['slot']:>4}  {lid:>8}  {desc:<20}  {min_s:>8}  {max_s:>10}  {'on':<8}  {l['lightning_address']}")
        print(f"            {l['lnurl']}")
    print()


def cmd_show(args):
    state = load_state()
    links = load_links()
    slot = get_slot(links, args.slot)
    live = api_get(state, f"/lnurlp/api/v1/links/{slot['id']}")
    print(json.dumps(live, indent=2))


def cmd_update(args):
    state = load_state()
    links = load_links()
    slot = get_slot(links, args.slot)
    lid = slot["id"]

    # Fetch current config from LNbits
    current = api_get(state, f"/lnurlp/api/v1/links/{lid}")

    payload = {
        "description": args.description or current.get("description", slot["description"]),
        "min":         args.min if args.min is not None else current.get("min", slot["min_sats"]),
        "max":         args.max if args.max is not None else current.get("max", slot.get("max_sats", 1000000)),
        "username":    args.username or current.get("username", slot["username"]),
        "domain":      current.get("domain", "soos-macbook-pro-2.tailb5a2b.ts.net"),
        "webhook_url": args.webhook or current.get("webhook_url", slot["webhook_url"]),
        "comment_chars": current.get("comment_chars", 255),
    }

    result = api_put(state, f"/lnurlp/api/v1/links/{lid}", payload)

    # Update local cache
    slot["description"] = payload["description"]
    slot["min_sats"] = payload["min"]
    slot["max_sats"] = payload["max"]
    slot["username"] = payload["username"]
    slot["webhook_url"] = payload["webhook_url"]
    slot["lightning_address"] = f"{payload['username']}@soos-macbook-pro-2.tailb5a2b.ts.net"
    PAYLINKS_FILE.write_text(json.dumps(links, indent=2))

    print(f"Slot {args.slot} updated:")
    print(f"  description : {payload['description']}")
    print(f"  min/max     : {int(payload['min'])} – {int(payload['max'])} sats")
    print(f"  username    : {payload['username']}")
    print(f"  lightning   : {slot['lightning_address']}")
    print(f"  webhook     : {payload['webhook_url']}")


def cmd_enable(args):
    _set_enabled(args.slot, True)


def cmd_disable(args):
    _set_enabled(args.slot, False)


def _set_enabled(slot_num: int, enabled: bool):
    state = load_state()
    links = load_links()
    slot = get_slot(links, slot_num)
    lid = slot["id"]

    current = api_get(state, f"/lnurlp/api/v1/links/{lid}")

    payload = {
        "description":  current.get("description", slot["description"]),
        "min":          current.get("min", slot["min_sats"]),
        "max":          current.get("max", slot.get("max_sats", 1000000)),
        "username":     current.get("username", slot["username"]),
        "domain":       current.get("domain", "soos-macbook-pro-2.tailb5a2b.ts.net"),
        "webhook_url":  current.get("webhook_url", slot["webhook_url"]),
        "comment_chars": current.get("comment_chars", 0),
        "is_unique":    not enabled,  # LNbits uses is_unique=True to make a link single-use / effectively disabled
    }

    api_put(state, f"/lnurlp/api/v1/links/{lid}", payload)
    status = "enabled" if enabled else "disabled"
    print(f"Slot {slot_num} ({slot['description']}) {status}.")


def cmd_qr(args):
    links = load_links()
    slot = get_slot(links, args.slot)
    lnurl = slot["lnurl"]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={lnurl}"
    print(f"\nSlot {args.slot} — {slot['description']}")
    print(f"Lightning Address : {slot['lightning_address']}")
    print(f"LNURL             : {lnurl}")
    print(f"QR URL            : {qr_url}")
    print(f"\nOpen QR in browser: open \"{qr_url}\"")


def main():
    parser = argparse.ArgumentParser(description="Manage TIMECHAIN LNURL paylinks")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List all 18 slots")

    p_show = sub.add_parser("show", help="Show full details for a slot")
    p_show.add_argument("slot", type=int)

    p_update = sub.add_parser("update", help="Update a slot's settings")
    p_update.add_argument("slot", type=int)
    p_update.add_argument("--description", type=str)
    p_update.add_argument("--min", type=int)
    p_update.add_argument("--max", type=int)
    p_update.add_argument("--username", type=str)
    p_update.add_argument("--webhook", type=str)

    p_enable = sub.add_parser("enable", help="Enable a slot")
    p_enable.add_argument("slot", type=int)

    p_disable = sub.add_parser("disable", help="Disable a slot")
    p_disable.add_argument("slot", type=int)

    p_qr = sub.add_parser("qr", help="Print QR URL for a slot")
    p_qr.add_argument("slot", type=int)

    args = parser.parse_args()

    if args.cmd == "list":       cmd_list(args)
    elif args.cmd == "show":     cmd_show(args)
    elif args.cmd == "update":   cmd_update(args)
    elif args.cmd == "enable":   cmd_enable(args)
    elif args.cmd == "disable":  cmd_disable(args)
    elif args.cmd == "qr":       cmd_qr(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
