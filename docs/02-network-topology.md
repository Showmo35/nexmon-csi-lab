# 2. Network topology

## The discovery that changed the plan

The original plan, carried over from the other PC, was: *plug in Ethernet, the
image already has `eth0: dhcp4: true`, it will Just Work.*

On this PC it would not have. Inspecting the wired interface before first boot
showed:

```
ipv4.method:      manual          <- static, not DHCP
ipv4.addresses:   10.0.0.250/24
ipv4.gateway:     --              <- no gateway
default route:    via wlp2s0 (Wi-Fi), not Ethernet
hosts responding on 10.0.0.0/24:  none
IPv6 router advertisement:        none
```

This machine also does SDR work — `uhd_find_devices` is installed and there is a
saved NetworkManager profile named `USRP` (`192.168.10.1/24`, the classic Ettus
host address). The wired port is configured for lab equipment, not for a LAN.

The cable turned out to run **directly from this PC to the Pi**. So the segment
is point-to-point: two devices, no router, no switch, **no DHCP server**.

### Why that breaks `dhcp4: true`

With no DHCP server, the Pi's `eth0` gets **no address at all**. And because the
image sets `optional: true`, boot does not block or warn — the Pi comes up
silently unreachable. `pi4b-nexmon.local` would not resolve, SSH would be
impossible, and with no monitor attached there would be nothing to look at.

This is a quiet failure mode: everything appears to boot fine, and the device is
simply absent from the network.

## The fix: static addresses on both ends

`network-config` on the boot partition was rewritten before first boot:

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      dhcp6: false
      addresses:
        - 10.0.0.100/24
      optional: true
```

Chosen so the Pi's `10.0.0.100` sits on the same `/24` as the PC's existing
`10.0.0.250` — no change needed on the PC side to establish basic connectivity.

The `wifis` section was dropped entirely at the same time (see
[01-hardware-and-image.md](01-hardware-and-image.md)).

### Confirmation it worked

On first boot the Pi claimed the address and answered ARP:

```
10.0.0.100 lladdr d8:3a:dd:f2:a3:3a REACHABLE
```

`d8:3a:dd` is the Raspberry Pi Ltd OUI — confirming both that cloud-init applied
the edited config and that the responding device was the Pi.

## Final addressing

| | PC | Pi |
|---|---|---|
| Interface | `enp1s0` | `eth0` |
| Address | `10.0.0.250/24` | `10.0.0.100/24` |
| Role | NAT gateway + DNS forwarder | client |
| Upstream | `wlp2s0` (eduroam), campus DHCP `172.28.x.x/20` | via the PC |

Round-trip time across the cable is ~0.33 ms.

## Name resolution

Both ends run `avahi`, and mDNS works across the direct link:

```
$ getent hosts pi4b-nexmon.local
10.0.0.100      pi4b-nexmon.local
```

Both paths are configured in SSH (`pi4b-nexmon` for the static IP,
`pi4b-nexmon-mdns` for mDNS). **Prefer the static IP** — it is deterministic and
does not depend on avahi being healthy on either end.

## Known wrinkle: DHCP pool overlap

Enabling NAT (see [04-internet-sharing.md](04-internet-sharing.md)) starts a
dnsmasq DHCP server with pool `10.0.0.1–10.0.0.241`. The Pi's static `.100` is
**inside that range**.

Harmless as long as this is a two-device cable — nothing else is present to
request a lease. If a switch and other devices are ever added to this segment,
move the Pi to `10.0.0.245` or narrow the pool, or dnsmasq may hand `.100` to
something else and cause an address conflict.

## Reverting

To restore the plain lab link (no NAT, no DHCP server):

```bash
./bin/restore-pc-network
```

or directly:

```bash
nmcli connection modify "Wired connection 1" ipv4.method manual ipv4.addresses 10.0.0.250/24
nmcli connection up "Wired connection 1"
```

This does not require `sudo` — polkit grants
`org.freedesktop.NetworkManager.settings.modify.system` to the desktop user.
