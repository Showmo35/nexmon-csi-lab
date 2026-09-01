# Lab routers

RF transmitters for controlled Nexmon CSI experiments. Neither router routes
anything — they exist to put known, steady 802.11 frames in the air for the Pi
to measure. Both have their **WAN/Internet port deliberately empty**.

Last updated: 2026-08-27

| Router | Firmware | Status | Use |
|---|---|---|---|
| [TP-Link TL-WDR4300](21-tl-wdr4300.md) | **DD-WRT v3.0-r30880** | **in service, CSI verified** | primary CSI transmitter |
| [TP-Link Talon AD7200](22-talon-ad7200.md) | OpenWrt | **not accessible** | 802.11ad / 60 GHz work, blocked on credentials |

## Current CSI transmitter

**TL-WDR4300**, two radios, both fixed-channel:

| SSID | BSSID | Channel | Freq |
|---|---|---|---|
| `nexmon-lab` | `60:E3:27:FB:61:53` | 1 | 2412 MHz |
| `nexmon-lab-5g` | `60:E3:27:FB:61:54` | 161 | 5805 MHz |

Point the Pi at either:

```bash
ssh pi4b-nexmon 'csi-enable 161/20 1 1 60:E3:27:FB:61:54'   # 5 GHz
ssh pi4b-nexmon 'csi-enable 1/20   1 1 60:E3:27:FB:61:53'   # 2.4 GHz
```

## Why not campus Wi-Fi or a phone hotspot

Both work, and both were used during bring-up, but neither is controlled:

| Source | Rate | Problem |
|---|---|---|
| Ambient campus APs (`WiFi@OSU`) | irregular | 4+ transmitters mixed together, none under your control |
| iPhone personal hotspot | 10 Hz | **iOS shuts the hotspot down after ~90 s with no client associated** |
| **TL-WDR4300** | 10 Hz (beacons) | none — always on, fixed channel, fixed position |

## Do not connect either router to campus Ethernet

An unregistered router on the OSU network is a policy problem and will likely be
blocked by NAC regardless. Nothing here needs an uplink: the Pi gets its internet
over the NAT'd direct cable to the PC (see `docs/04-internet-sharing.md`), and
the routers only need to transmit.

## Credentials

Not recorded here, deliberately. Router admin passwords and WPA2 keys live in
your password manager, not in a git repo. Note that **CSI collection needs no
Wi-Fi password at all** — the Pi sniffs in monitor mode and never associates.
