# 6. Troubleshooting

Run `./bin/csi-checkup` first — it covers most of the checks below in one go.

## The Pi is unreachable

Work outward from the physical layer; each step tells you whether to keep going.

### 1. Is the cable live?

```bash
cat /sys/class/net/enp1s0/carrier      # 1 = link up, 0 = no link
cat /sys/class/net/enp1s0/speed        # expect 1000
```

`carrier=0` means no link: the Pi is powered off, the cable is unseated, or the
Pi has not brought up its interface yet.

**Useful trick:** a Pi 4B negotiates Ethernet link as soon as it has power, even
before an OS boots. So `carrier=1` with no ping usually means *powered but not
booted* (or booted without a working network config) — not a cabling fault.

### 2. Is the PC's own address right?

```bash
ip -br addr show enp1s0                # expect 10.0.0.250/24
```

If this is missing or wrong, the NAT/shared-mode change may have reset it. Fix:

```bash
nmcli connection modify "Wired connection 1" ipv4.addresses 10.0.0.250/24
nmcli connection up "Wired connection 1"
```

### 3. Does the Pi answer at layer 2?

```bash
ping -c3 10.0.0.100
ip neigh show dev enp1s0
```

- `lladdr d8:3a:dd:...  REACHABLE` — the Pi is alive and on the right subnet.
  `d8:3a:dd` is the Raspberry Pi Ltd OUI.
- `INCOMPLETE` or `FAILED` — nothing is answering ARP at that address.

### 4. Still nothing — is it mid-reboot?

First boot reboots once, and any `apt` kernel upgrade means another. Wait for
*sustained* reachability rather than a single ping (see
[03-ssh-access.md](03-ssh-access.md) for the streak loop).

### 5. Last resort — serial console

`user-data` sets `rpi: interfaces: serial: true`, so a USB-TTL adapter on the
GPIO header gives a console at **115200 baud** even with networking completely
broken. This is the escape hatch when the network config itself is the problem.

## `pi4b-nexmon.local` does not resolve

mDNS is a convenience here, not the primary path — **use `ssh pi4b-nexmon`**,
which goes to the static IP and does not depend on avahi.

If you want mDNS working:

```bash
systemctl is-active avahi-daemon        # on the PC
grep '^hosts:' /etc/nsswitch.conf       # needs mdns4_minimal
avahi-resolve -4 -n pi4b-nexmon.local
```

Note `nsswitch.conf` here uses `mdns4_minimal` — **IPv4 only**. Name resolution
over IPv6 mDNS will not work; switch to `mdns_minimal` if that is ever needed.

## SSH fails

### `Permission denied (publickey)`

The Pi has `ssh_pwauth: false`, so key auth is the only option.

```bash
ssh-keygen -lf ~/.ssh/pi4b_nexmon.pub
# expect SHA256:5XBaWiqFHa00KMlT0dwGD0J5hTdimmax1eo4Jb5BApk
ssh -v pi4b-nexmon 2>&1 | grep -i "offering\|accepted"
```

If the key is genuinely lost, the boot partition is the recovery route: mount the
USB drive's `bootfs` on another machine and rewrite `ssh_authorized_keys` — but
note that **cloud-init only consumes `user-data` on first boot**, so on an
already-booted system you must instead edit
`/home/nexmon/.ssh/authorized_keys` directly (via serial console or by mounting
`rootfs`).

### `REMOTE HOST IDENTIFICATION HAS CHANGED`

Expected if the Pi was reflashed — it generates new host keys. Clear the stale
entry:

```bash
ssh-keygen -R 10.0.0.100
ssh-keygen -R pi4b-nexmon.local
```

### Connection hangs rather than refusing

Usually the Pi is mid-boot and `sshd` has not started. Check the port directly:

```bash
nc -z -w3 10.0.0.100 22 && echo open || echo closed
```

## The Pi has no internet

```bash
ssh pi4b-nexmon 'ip route | grep default'    # expect: default via 10.0.0.250
cat /proc/sys/net/ipv4/ip_forward            # on the PC, expect 1
pgrep -a dnsmasq                             # on the PC, expect a shared-mode instance
```

Common causes:

- **Shared mode was reverted** — re-run the `nmcli ... ipv4.method shared` command
  from [04-internet-sharing.md](04-internet-sharing.md).
- **The Pi lost its default route** — the runtime `ip route add` does not survive
  a reboot on its own; the persistent setting is `ipv4.gateway` on the
  `netplan-eth0` connection. Verify with
  `nmcli -f ipv4.gateway,ipv4.dns connection show netplan-eth0`.
- **The PC's Wi-Fi is down** — NAT has nothing to forward to. Check `wlp2s0`.
- **Upstream captive portal / campus restrictions** — eduroam may block or
  intercept. Test from the PC first; if the PC cannot reach the internet, the Pi
  certainly cannot.

### `apt` stalls on IPv6

Should not happen (see [04-internet-sharing.md](04-internet-sharing.md)), but if
IPv6 ever becomes partially configured:

```bash
echo 'Acquire::ForceIPv4 "true";' | sudo tee /etc/apt/apt.conf.d/99force-ipv4
```

## `apt` breakage after the Python 2.7 step

The install temporarily adds an EOL Debian Stretch repository. If `apt` ends up
in a bad state, restore the snapshot taken beforehand:

```bash
sudo cp -a /root/nexmon-backup/sources.list /etc/apt/sources.list
sudo rm -rf /etc/apt/sources.list.d
sudo cp -a /root/nexmon-backup/sources.list.d /etc/apt/
sudo apt-get update
```

Then check nothing from Stretch is still installed:

```bash
apt list --installed 2>/dev/null | grep -i stretch
```

## Wi-Fi / `wlan0` notes

`wlan0` is intentionally **DOWN and unmanaged** — the `wifis` section was removed
from `network-config`. This is the desired state for Nexmon CSI, which drives the
interface into monitor mode itself.

Do **not** "fix" this by reconnecting `wlan0` to a network. If normal Wi-Fi is
ever needed alongside CSI work, be aware that NetworkManager managing the
interface can conflict with patched firmware.

The `eduroam` entry from the original image could never have worked —
WPA2-Enterprise cannot be expressed through Raspberry Pi Imager's basic Wi-Fi
field. Connecting to eduroam would require a full `wpa_supplicant` configuration
with EAP identity, password, and phase2 settings.

## Recovering a completely unbootable Pi

The boot partition is FAT32 and readable on any PC:

1. Power off the Pi, move the USB drive to a PC
2. It mounts as `bootfs` — `cmdline.txt`, `config.txt`, `user-data`,
   `network-config` are all editable there
3. `rootfs` (ext4) is also mountable on Linux for deeper repair

Confirm no microSD card is inserted — the Pi 4B tries SD before USB.
