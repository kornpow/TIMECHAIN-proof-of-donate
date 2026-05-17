# LND Credentials — Minimal Macaroon

LNbits needs to talk to your LND node to create and monitor Lightning invoices.
You should **never** use `admin.macaroon` in production — it has full control over
your node. Instead, bake a minimal macaroon with only the permissions LNbits needs.

---

## 1. Bake the Macaroon

Run this on the machine where LND is running (Umbrel, Start9, bare metal, etc.):

```bash
lncli bakemacaroon \
  invoices:read invoices:write \
  info:read \
  offchain:read offchain:write
```

This outputs a hex-encoded macaroon string. Copy it.

### Why each permission

| Permission | Why it's needed |
|---|---|
| `invoices:read` | LNbits polls for invoice settlement |
| `invoices:write` | LNbits creates new Lightning invoices |
| `info:read` | LNbits health checks — reads node info / sync state |
| `offchain:read` | Reads channel and payment state |
| `offchain:write` | Sends payments (needed if you want LNbits to pay out) |

> **Minimal setup:** If you only need to *receive* payments (the typical case for
> this project), you can drop `offchain:write`. The webhook only receives inbound
> payments; it never sends.

---

## 2. Export as Hex

If `lncli bakemacaroon` doesn't print hex directly (older versions write a file),
convert it:

```bash
# Find the baked macaroon file (lncli will tell you the path)
xxd -p -c 10000 ~/.lnd/data/chain/bitcoin/mainnet/your-baked.macaroon | tr -d '\n'
```

This is the value you put in `.env` as `LND_REST_MACAROON`.

---

## 3. Copy the TLS Certificate

LND's REST API requires TLS. Copy the cert to this project:

```bash
# From your LND node
scp user@your-lnd-node:~/.lnd/tls.cert ./lnd-tls.cert
```

Or if you're on the same machine:

```bash
cp ~/.lnd/tls.cert ./lnd-tls.cert
```

The file `lnd-tls.cert` is gitignored. The Ansible playbook copies it to the
deployment server automatically.

---

## 4. Configure .env

Copy `ansible/env.example` to `.env` and fill in:

```bash
LNBITS_BACKEND_WALLET_CLASS=LndRestWallet

# Tailscale IP or LAN IP of your LND node
LND_REST_ENDPOINT=https://100.x.x.x:8080

# Hex macaroon from step 2
LND_REST_MACAROON=0201036c6e6402...

# Leave blank — the Ansible playbook copies lnd-tls.cert to the right place
LND_REST_CERT=
```

> **Why blank for `LND_REST_CERT`?** The Ansible playbook copies `lnd-tls.cert`
> directly into the LNbits package directory and sets the path via a systemd
> environment variable. You don't need to set the path in `.env`.

---

## 5. Reach Your Node Over Tailscale

Your LND node and the deployment server (Pi/VPS) must both be on the same
Tailscale network for `LND_REST_ENDPOINT` to resolve. See
[`tailscale.md`](tailscale.md) for setup details.

---

## Troubleshooting

**"permission denied" errors from LNbits:**
Re-bake the macaroon and make sure all four permissions are present.

**TLS verification errors:**
Make sure `lnd-tls.cert` was copied from the correct node and hasn't been
regenerated since (LND regenerates `tls.cert` if you change its IP/domain config).

**Can't reach `LND_REST_ENDPOINT`:**
Check that both machines are on Tailscale and that LND is bound to `0.0.0.0`
(not just `127.0.0.1`). On Umbrel: Settings → Advanced → REST API should show
the Tailscale IP.
