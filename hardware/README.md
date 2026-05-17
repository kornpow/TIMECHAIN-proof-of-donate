# Hardware — Clock Modification

## What This Does

A cuckoo clock is modified so that whenever a Bitcoin Lightning payment arrives,
an electromagnet pulls on the clock's chime gear, triggering the full cuckoo chime
cycle — exactly as if the clock had struck the hour on its own.

The clock's internal mechanism is **not permanently modified**. The electromagnet
is externally mounted against the gear. The clock still keeps time and chimes
normally on the hour.

---

## How It Triggers

```
Wall outlet
    └── Shelly Plus Plug US  (switched on/off via WiFi HTTP API)
            └── 12V ~2A power supply  (barrel jack)
                    └── Electromagnet
                            └── Mounted against chime gear inside cuckoo clock
```

1. A Lightning payment arrives → LNbits fires a webhook → Python script runs
2. The script sends an HTTP POST to the Shelly outlet to turn it ON
3. The Shelly powers the 12V PSU → current flows through the electromagnet
4. The magnet pulls the chime gear → the clock's cuckoo mechanism fires
5. After a configurable delay the script turns the Shelly OFF
6. The Shelly also has a hardware `auto_off` timer (2 seconds) as a failsafe —
   the magnet can never be left energized if the software fails

The `auto_off` safety timer is configured automatically by the Ansible playbook
(`ansible/deploy.yml`), but can also be set manually:

```bash
curl -X POST http://172.16.4.55/rpc/Switch.SetConfig \
  -H "Content-Type: application/json" \
  -d '{"id":0,"config":{"auto_off":true,"auto_off_delay":2}}'
```

---

## Parts List

| Part | Details | Approx. Cost |
|---|---|---|
| Cuckoo clock | Any standard cuckoo clock with a gear-driven chime mechanism | varies |
| Electromagnet | ~$11, 12V DC, mounting holes, pull-type — [link TBD] | ~$11 |
| 12V ~2A power supply | Barrel jack (5.5mm × 2.1mm), center positive, generic | on-hand / ~$10 |
| Shelly Plus Plug US | Smart outlet — HTTP API + WiFi, controls the 12V PSU | ~$20 |
| Barrel jack cable | Male barrel jack to screw terminals or bare wire | ~$2 |
| Mounting hardware | Small screws or zip ties to attach the electromagnet | ~$1 |

**Total estimated cost (excluding clock): ~$44**

---

## Mounting the Electromagnet

1. Open the back panel of the cuckoo clock to expose the gear mechanism
2. Identify the gear that initiates the chime cycle (it will be pulled or nudged
   by the hour cam during a normal chime strike)
3. Position the electromagnet so its face is ~1–2mm from the target gear
4. Secure the electromagnet to the clock housing with small screws or zip ties —
   do not glue anything to the clock mechanism itself
5. Route the wires out the back panel and down to the barrel jack connector
6. Plug barrel jack into the 12V PSU output
7. Plug the PSU into the Shelly outlet

> **Tip:** Test the magnet position with a short `./start.sh outlet 1` pulse before
> closing up the clock. The gear should pull cleanly and release without binding.

---

## Configuring the Shelly Outlet

The Shelly must be on your local WiFi network. Configure it via the Shelly app or
web UI, then update the IP in `main.py` and `start.sh` (`SHELLY_HOST`).

Test the outlet manually:

```bash
./start.sh outlet 1   # turn on for 1 second
./start.sh outlet 2   # turn on for 2 seconds
```

See the Shelly web UI at `http://172.16.4.55` (or whatever IP it received from
your router). Set a static DHCP lease so the IP never changes.

---

## Photos

See [`photos/`](photos/) for build photos.

---

## 3D Printed Parts

See [`3d-parts/`](3d-parts/) for printable mounting brackets and enclosures
(planned — not yet available).
