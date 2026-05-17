# Cloudflare Tunnel

LNURL payments **require a publicly resolvable HTTPS domain**. When a donor scans
the QR code, their Lightning wallet makes an HTTP request to your LNURL endpoint
to fetch payment parameters. That request comes from the internet — it cannot
reach a private LAN IP or a `localhost` address.

The Cloudflare Tunnel gives you a stable public HTTPS domain that routes through
to your local server without opening any firewall ports.

---

## Domains Used

| Hostname | Routes to | Purpose |
|---|---|---|
| `timechain.win` | `localhost:5001` | LNbits UI + LNURL resolution |
| `pay.timechain.win` | `localhost:5001` | LNURL paylink endpoint |
| `webhook.timechain.win` | `localhost:8000` | Webhook server (optional external access) |

---

## 1. Install cloudflared (Mac)

```bash
brew install cloudflared
```

---

## 2. Authenticate

```bash
cloudflared tunnel login
```

This opens a browser window. Log in to your Cloudflare account and authorize the
domain you want to use. A credentials file is saved at
`~/.cloudflared/cert.pem`.

---

## 3. Create the Tunnel (one-time)

```bash
cloudflared tunnel create timechain
```

This outputs:
- A **tunnel ID** (UUID, e.g. `dcfbf63a-3fb7-4fc5-8759-f46bba7bb77f`)
- A **credentials JSON file** at `~/.cloudflared/<tunnel-id>.json`

Copy the credentials file into the project root (it's gitignored):

```bash
cp ~/.cloudflared/<tunnel-id>.json ./cloudflare-tunnel-credentials.json
```

Update `cloudflare_tunnel_id` in `ansible/deploy.yml` with your tunnel ID.

---

## 4. Set DNS Records

In the Cloudflare dashboard (or via CLI), add CNAME records pointing each
hostname to your tunnel:

```bash
cloudflared tunnel route dns timechain timechain.win
cloudflared tunnel route dns timechain pay.timechain.win
cloudflared tunnel route dns timechain webhook.timechain.win
```

Or manually in the Cloudflare DNS dashboard:
- Type: `CNAME`
- Name: `timechain.win` (and subdomains)
- Target: `<tunnel-id>.cfargotunnel.com`
- Proxy: **Proxied** (orange cloud)

---

## 5. Deploy

The Ansible playbook handles everything on the server side:

```bash
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

It will:
1. Download and install `cloudflared`
2. Copy `cloudflare-tunnel-credentials.json` → `~/.cloudflared/credentials.json`
3. Write `~/.cloudflared/config.yml` with the tunnel ID and ingress rules
4. Install and start a `cloudflared` systemd service

---

## 6. Verify

Once deployed, test that the tunnel is up:

```bash
curl https://timechain.win/api/v1/health
# should return {"status": "UP", ...}

curl https://pay.timechain.win/api/v1/health
# same
```

Check tunnel status on the server:

```bash
sudo systemctl status cloudflared
journalctl -u cloudflared -f
```

---

## Re-deploying After Credential Changes

If you rotate the tunnel credentials:

1. Replace `cloudflare-tunnel-credentials.json` in the project root
2. Re-run the playbook with the `app` tag:
   ```bash
   ansible-playbook -i ansible/inventory.ini ansible/deploy.yml --tags app
   ```

---

## Troubleshooting

**`ERR_TUNNEL_CONNECTION_FAILED`:**
The `cloudflared` service on the server is not running or cannot reach
Cloudflare. Check `journalctl -u cloudflared`.

**LNURL not resolving / QR code doesn't work:**
Make sure `LNBITS_PUBLIC_URL` in `.env` matches the public domain exactly
(e.g. `https://pay.timechain.win`). Re-run `setup_lnbits.py` after changing it.

**DNS not propagating:**
Cloudflare DNS is usually instant but can take a few minutes. Verify with
`dig timechain.win` — the CNAME should point to `<tunnel-id>.cfargotunnel.com`.
