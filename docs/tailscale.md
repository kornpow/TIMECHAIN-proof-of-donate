# Tailscale

Tailscale serves two roles in this project:

1. **Private access to your LND node** — the deployment server (Pi/VPS) reaches
   your LND node's REST API over a private Tailscale IP, without exposing LND
   to the public internet
2. **Alternative public tunnel** — Tailscale Funnel can expose port 5001 publicly
   as an alternative to the Cloudflare tunnel (useful for dev/testing)

---

## Role 1 — Private LND Access

Your LND node (Umbrel, Start9, bare metal, etc.) sits behind your home router
with no open ports. The deployment server running LNbits needs to reach LND's
REST API at port 8080.

Tailscale solves this: both machines join the same tailnet and get stable private
IPs (`100.x.x.x`) that are reachable from anywhere.

### Setup

**On your LND node:**

Install Tailscale and authenticate:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

After joining the tailnet, note the machine's Tailscale IP from
`tailscale ip -4` or the Tailscale admin console.

**Make LND listen on its Tailscale IP** (or all interfaces):

On Umbrel/Start9, the REST API is already bound to `0.0.0.0:8080`. On bare
metal, check `~/.lnd/lnd.conf`:

```ini
[Application Options]
restlisten=0.0.0.0:8080
```

Restart LND after any config change.

**Set `LND_REST_ENDPOINT` in `.env`:**

```bash
LND_REST_ENDPOINT=https://100.x.x.x:8080
```

Use the Tailscale IP of your LND node. It never changes as long as the node
stays in your tailnet.

---

## Role 2 — Public Tunnel (Alternative to Cloudflare)

Tailscale Funnel exposes a local port publicly via a `*.ts.net` HTTPS URL. This
is useful for development or if you don't have a custom domain.

```bash
# On the machine running LNbits
tailscale funnel --bg 5001
```

This gives you a URL like `https://your-machine.tail1234.ts.net`. Set it in
`.env`:

```bash
LNBITS_PUBLIC_URL=https://your-machine.tail1234.ts.net
```

Then re-run `setup_lnbits.py` to regenerate the LNURL QR code with the new URL.

> **Limitation:** Tailscale Funnel URLs include a random subdomain and change if
> you reset your tailnet. For a permanent production URL, use the Cloudflare
> tunnel with a real domain instead — see [`cloudflare-tunnel.md`](cloudflare-tunnel.md).

---

## Tailscale Auth Key for Ansible

The Ansible playbook installs Tailscale on the deployment server and
authenticates it automatically using an auth key.

**Generate an auth key:**

1. Go to [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
2. Generate a key — use **Reusable** if you may redeploy, **Ephemeral** if the
   server should auto-remove from the tailnet when it goes offline
3. Set it as an environment variable before running the playbook:

```bash
export TAILSCALE_AUTH_KEY=tskey-auth-...
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

The playbook runs `tailscale up --authkey $TAILSCALE_AUTH_KEY --accept-routes`
to join the tailnet.

---

## Verifying the Connection

From the deployment server, confirm it can reach LND:

```bash
curl -k https://100.x.x.x:8080/v1/getinfo \
  --header "Grpc-Metadata-macaroon: $(cat your-baked.macaroon | xxd -p -c 10000)"
```

Should return your node's public key, alias, and sync status.

If this works, LNbits will be able to connect.
