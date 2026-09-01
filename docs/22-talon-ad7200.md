# TP-Link Talon AD7200 — OpenWrt, not currently accessible

Tri-band router: 2.4 GHz, 5 GHz, and **60 GHz (802.11ad / WiGig)**. The 60 GHz
radio is what makes this model interesting — it is the standard platform for
802.11ad research and the target of SEEMOO's **Talon Tools**, from the same lab
that produced nexmon.

**Status: blocked on credentials.** Not in service as a CSI transmitter; the
[TL-WDR4300](tl-wdr4300.md) is used instead.

## What was determined

The unit does **not** run stock TP-Link firmware. Evidence gathered over a direct
Ethernet cable:

| Probe | Result | Meaning |
|---|---|---|
| Link | up, 1000 Mb/s full duplex | cable and hardware fine |
| IPv6 all-nodes multicast (`ff02::1`) | replies from `fe80::52c7:bfff:fe92:ffc4` | device alive |
| MAC (decoded from EUI-64) | `50:c7:bf:92:ff:c4` | `50:C7:BF` = TP-Link OUI |
| IPv4 `192.168.0.1`, `192.168.5.2` | no ARP reply | not on either address |
| DHCP request | no response | DHCP server disabled |
| TCP 80 / 443 / 8080 / 8443 | closed | **no web UI — LuCI not installed** |
| TCP **22** | open, banner `SSH-2.0-dropbear` | **OpenWrt/LEDE** |
| TCP **53** | open | dnsmasq running |
| SSH host key | `ssh-rsa` only | old Dropbear build |

Stock TP-Link firmware is the exact inverse: web UI on port 80, no SSH. Dropbear
plus dnsmasq plus no LuCI is an OpenWrt device intended to be managed over SSH.

The label reads `192.168.5.2`, but nothing answered there on either the WAN or a
LAN port — so either that is stale, or the LAN interface is configured
differently from what the label claims.

## How to get in when you have credentials

It is reachable over IPv6 link-local without knowing its IPv4 address. Note the
`%enp1s0` zone index and the legacy algorithm flags — modern OpenSSH rejects this
router's `ssh-rsa` host key by default:

```bash
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa \
    root@fe80::52c7:bfff:fe92:ffc4%enp1s0
```

Rediscover the link-local address if the unit is ever reflashed:

```bash
ping -6 -c3 -I enp1s0 ff02::1     # every device on the wire replies
```

Once in, `uci show network` and `uci show wireless` reveal the real addressing
and radio configuration.

## Options

1. **Get the password** from whoever flashed it — preferable, since the OpenWrt
   image may carry lab-specific 802.11ad configuration worth keeping.
2. **Factory reset** — returns to whatever the OpenWrt image defaults to
   (typically `192.168.1.1`, root with no password, LuCI still absent if it was
   not built in). **This destroys the existing configuration**, which on a shared
   lab device may belong to someone else's experiment. Ask first.

## Relevance to Nexmon CSI

For CSI work with the Pi, this router offers nothing the WDR4300 does not — the
Pi's BCM43455c0 is **2.4/5 GHz only and physically cannot see 60 GHz**. Its value
is if 802.11ad enters scope, in which case Talon Tools and this hardware are the
established path.
