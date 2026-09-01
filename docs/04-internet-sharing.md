# 4. Internet sharing (NAT)

## Why this was needed

A direct PC-to-Pi cable gives connectivity between the two machines but **no
route to the internet** — no gateway, no DNS. That is fine for SSH, but the
Nexmon CSI install needs `apt` (build toolchain, dependencies) and `git clone`
from GitHub. So the PC has to act as a NAT gateway.

## PC side — NetworkManager shared mode

No `sudo` and no manual `iptables` were needed. NetworkManager's **shared** mode
does the whole job as root on our behalf: it enables IP forwarding, installs
masquerade rules toward the upstream interface, and starts a dnsmasq instance for
DNS and DHCP.

This worked because polkit grants the desktop user
`org.freedesktop.NetworkManager.settings.modify.system: yes` — check with
`nmcli general permissions`.

```bash
nmcli connection modify "Wired connection 1" ipv4.method shared ipv4.addresses 10.0.0.250/24
nmcli connection up "Wired connection 1"
```

Pinning `ipv4.addresses` matters. Left to itself, shared mode picks
`10.42.0.1/24`, which would have stranded the Pi's static `10.0.0.100`.

### What that produced

```
/proc/sys/net/ipv4/ip_forward       1
dnsmasq listening                   10.0.0.250:53  (DNS forwarder)
dnsmasq DHCP range                  10.0.0.1 - 10.0.0.241
masquerade                          enp1s0 -> wlp2s0
```

The Pi keeps its static `10.0.0.100`; it never uses the DHCP server. See the
pool-overlap warning in [02-network-topology.md](02-network-topology.md).

## Pi side — gateway and DNS

Requires `sudo` on the Pi (interactive password at the time this was run):

```bash
# immediate, does not disturb the live interface
sudo ip route add default via 10.0.0.250

# persistent across reboots
sudo nmcli connection modify netplan-eth0 \
     ipv4.gateway 10.0.0.250 \
     ipv4.dns "10.0.0.250 8.8.8.8"
```

The split is deliberate. `ip route add` takes effect instantly **without
touching `eth0`**, so the SSH session issuing it does not drop. `nmcli
connection up` was deliberately *avoided* — it bounces the interface and can hang
the very session running it.

The Pi's NetworkManager connection is named `netplan-eth0` (netplan renders
cloud-init's network config into NetworkManager).

## Verification

```
Pi -> PC gateway     10.0.0.250     0% loss, 0.35 ms
Pi -> internet (IP)  1.1.1.1        0% loss, 12.5 ms
deb.debian.org       HTTP  200      0.09 s
deb.debian.org sec   HTTPS 200      0.10 s
archive.raspberrypi.com HTTPS 200   0.53 s
github.com           HTTPS 200      0.25 s
apt-get update       27.2 MB @ 3.9 MB/s
```

## The IPv6 gotcha (resolved itself)

DNS lookups of `deb.debian.org` return **AAAA records first**:

```
$ getent hosts deb.debian.org
2a04:4e42:400::644 debian.map.fastlydns.net deb.debian.org
...
```

The Pi has **no IPv6 route to the internet** — NAT was configured for IPv4 only.
A common failure mode here is `apt` trying IPv6, stalling, and timing out.

It did **not** happen, and the reason is worth recording: because the Pi has no
IPv6 default route at all, glibc's RFC 6724 address-selection rules deprioritise
the AAAA answers, and connections transparently choose IPv4. Verified — `curl`
to `deb.debian.org` resolved to `151.101.130.132` (IPv4) in 0.09 s.

So **no `Acquire::ForceIPv4` workaround is needed.** If IPv6 is ever partially
configured on this link, that could change: a *broken but present* IPv6 route is
worse than none, and would reintroduce the stall. In that case:

```bash
echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4
```

## Reverting

```bash
./bin/restore-pc-network
```

This returns the PC's wired connection to `ipv4.method=manual` and stops the
NAT and dnsmasq. The Pi keeps its static address and stays reachable over the
cable; it simply loses internet access.
