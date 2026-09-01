# 5. Nexmon CSI — compatibility and install

> **Status: COMPLETE AND VALIDATED.** All nine steps done, CSI frames captured
> off the air, payload decoded and sanity-checked, and firmware persistence
> confirmed across a full power cycle. Verified 2026-08-27.

## The compatibility question

The Pi runs **Debian 13 (trixie), kernel 6.18.x, firmware 7.45.265**. All three
are far newer than nexmon_csi's headline requirements, which are commonly quoted
as *kernel 4.19 / 5.4 / 5.10* and *firmware 7_45_189*. That looked like a
blocker. It is not, but only via a specific path.

### Finding 1 — the installed firmware version does not matter

nexmon_csi patches **firmware 7_45_189** and installs the patched blob through
`update-alternatives`. It does **not** patch whatever firmware is currently on
the device. So the stock `7.45.265` is simply superseded.

This matters because upstream explicitly does *not* provide patches for newer
firmware — [nexmon discussion #605](https://github.com/seemoo-lab/nexmon/discussions/605)
has a maintainer stating there is no patch for `7.45.241`, recommending `7.45.206`
instead. It would be easy to conclude from that thread that `7.45.265` is fatal.
It is not, because the patched firmware replaces rather than extends it.

### Finding 2 — kernel 6.x is supported via `Makefile.rpi`

The historical blocker for new kernels was that nexmon_csi required a **modified
`brcmfmac` driver**, which had to be built per kernel version and only existed
for a few.

[nexmon_csi discussion #395](https://github.com/seemoo-lab/nexmon_csi/discussions/395)
documents a newer path using `Makefile.rpi` that **no longer requires a modified
driver**, managing firmware through `update-alternatives` instead. It confirms:

- kernel 6.x — works
- Raspberry Pi OS **Trixie** — confirmed
- **Pi 4B and Pi 5** — no modification needed

The 16k-page workaround in that guide (`kernel=kernel8.img`) is **Pi 5 only** and
does not apply here.

### Verdict

| | |
|---|---|
| Chip `bcm43455c0` | supported — exactly what nexmon_csi targets |
| Kernel 6.18.x | supported via `Makefile.rpi` |
| Trixie | confirmed working upstream |
| Stock firmware 7.45.265 | irrelevant — replaced by patched 7_45_189 |

## Environment survey

Checked on the Pi before starting:

| Check | Result |
|---|---|
| Free disk | 48 GB |
| RAM | 7.6 GiB |
| `linux-headers-rpi-v8` | `1:6.18.34-1+rpt1` — exact match for running kernel |
| Build deps in trixie | all available |
| `python2.7` in trixie | **not available** — see below |
| `armhf` foreign arch | **already enabled** |

Two of the upstream steps are therefore no-ops on this image: `armhf` is already
enabled (step 3), and the Pi 5 page-size workaround does not apply (step 1).

Kernel headers are listed above for completeness but are **not required** by this
path, since no driver module is rebuilt.

## The Python 2.7 risk

Upstream step 4 requires **Python 2.7**, which Trixie removed entirely
(confirmed — no candidate in any configured suite). The documented workaround is
to temporarily add a **Debian Stretch** repository, install `python2.7`, then
restore the original sources.

Stretch reached EOL in 2020. Pointing a Trixie system at it, even briefly, risks
pulling in old libraries if pinning is not tight. **This is the single riskiest
step of the install.**

Mitigations applied:

- `/etc/apt/sources.list` and `/etc/apt/sources.list.d/` snapshotted to
  `/root/nexmon-backup/` before any change
- Stretch used only to install `python2.7`, nothing else
- sources restored immediately afterwards, followed by `apt update` to confirm
  the system is clean

The Pi uses deb822-format sources (`.sources` files in
`/etc/apt/sources.list.d/`), not the classic one-line format:

- `debian.sources` — trixie, trixie-updates, trixie-security
- `raspi.sources` — archive.raspberrypi.com trixie

## Install procedure

Following [discussion #395](https://github.com/seemoo-lab/nexmon_csi/discussions/395).

| Step | Action | Status |
|---|---|---|
| 1 | Pi 5 16k-page workaround | **skipped** — Pi 4B |
| 2 | `apt full-upgrade` + build dependencies | **done** |
| 3 | armhf multilib + libisl/libmpfr symlinks | **done** |
| 4 | Python 2.7 | **done** — deviation, see below |
| 5 | Clone nexmon, patch b43-beautifier, `make` | **done** |
| 6 | Build `nexutil` with `USE_VENDOR_CMD=1` | **done** |
| 7 | Clone `nexmon_csi` into the patches directory | **done** |
| 8 | `install-firmware`, `unmanage`, `reload-full` | **done** — with fixes, see below |
| 9 | Configure CSI via `nexutil`, enable monitor mode | **done** |

## What was actually done, step by step

### Step 2 — upgrade and dependencies

`full-upgrade` moved the kernel `6.18.34 → 6.18.39` and updated
`firmware-brcm80211`. Rebooted after; the Pi came back in 57 seconds and the
static addressing and default route both survived (`proto static` on the route
confirms it came from the persistent NetworkManager setting, not the runtime
`ip route add`).

### Step 3 — armhf multilib

`armhf` was already enabled on this image, so only the libraries and symlinks
were needed:

```bash
sudo apt-get install libc6:armhf libisl23:armhf libmpfr6:armhf libmpc3:armhf libstdc++6:armhf
sudo ln -sf /usr/lib/arm-linux-gnueabihf/libisl.so.23 /usr/lib/arm-linux-gnueabihf/libisl.so.10
sudo ln -sf /usr/lib/arm-linux-gnueabihf/libmpfr.so.6 /usr/lib/arm-linux-gnueabihf/libmpfr.so.4
```

The sonames on Trixie matched the guide's assumptions exactly (`libisl.so.23`,
`libmpfr.so.6`). Note these symlinks are deliberate ABI fictions — nexmon's
bundled toolchain was linked against `libisl.so.10` and `libmpfr.so.4`, and this
points those names at much newer libraries. Upstream reports it works; if the
toolchain ever segfaults strangely, this is a place to look.

### Step 4 — Python 2.7, and a deliberate deviation

**The upstream commands were NOT followed verbatim here.** Running them as
written would have been worse than the guide implies.

Simulating the documented `apt install python2.7` first (`apt-get -s`) showed:

```
Remv mailcap [3.74]
Remv media-types [13.0.0] [python3.13:arm64 libpython3.13-stdlib:arm64 ]
Inst mime-support (3.60 Debian:9.13/oldoldstable)
Inst libssl1.1 (1.1.0l-1~deb9u1 Debian:9.13/oldoldstable)
Inst libtinfo5, libncursesw5, libreadline7 ... (all Debian 9)
```

Stretch's `mime-support` conflicts with Trixie's `media-types`, so apt proposed
removing `media-types` and pulling in a set of EOL Debian 9 libraries including
`libssl1.1`.

**How bad was it really?** Less bad than it first looks. Both `python3.13` and
`libpython3.13-stdlib` declare:

```
Depends: media-types | mime-support
```

That is an **OR** — installing `mime-support` satisfies it, so Python 3 would
*not* have broken. Worth knowing, because apt's bracket notation
(`Remv media-types [...] [python3.13:arm64 ...]`) reads alarmingly and is easy
to misinterpret as "these will break".

**What was done instead:** `python2.7-minimal` installs cleanly with **2
packages, zero removals, and no conflict**:

```bash
sudo apt-get install python2.7-minimal     # -> Python 2.7.13
```

This provides `/usr/bin/python2.7`, which is exactly what the patched
`b43-beautifier` shebang invokes. `media-types` was never touched, no EOL
libraries were installed, and `python3.13` was left completely alone —
verified afterwards with `apt-get check` and by importing `mimetypes`, `ssl`
and `sqlite3` under Python 3.

**Caveat:** `python2.7-minimal` ships a reduced standard library. If a nexmon
build script fails on a missing Python 2 module, the fallback is the full
`python2.7` package — which, per the analysis above, is safe to install despite
the alarming simulation output.

**Exposure window:** the Stretch repository was added, used for one install, and
removed immediately. Verified afterwards that no `stretch` reference remains in
`/etc/apt/sources.list` or `/etc/apt/sources.list.d/`, and that `apt-get update`
and `apt-get check` are both clean.

The Stretch line was **GPG-verified** — the Debian 9 archive key is still in
Trixie's keyring, so no `[trusted=yes]` override was needed.

### Step 5 — nexmon build

```bash
git clone --depth 1 https://github.com/seemoo-lab/nexmon.git   # 2.4 GB, 34803 files
cd nexmon
source setup_env.sh
sed -i '1 s/$/2.7/' $NEXMON_ROOT/buildtools/b43-v3/debug/b43-beautifier
make
```

The `sed` rewrites the b43-beautifier shebang from `#!/usr/bin/env python` to
`#!/usr/bin/env python2.7`, pinning it to the Python 2 interpreter rather than
whatever `python` happens to resolve to (on Trixie, nothing).

Build log is kept on the Pi at `~/nexmon-build.log`.

### Steps 6-7 - nexutil and nexmon_csi

```bash
cd $NEXMON_ROOT/utilities/nexutil
sudo -E make install USE_VENDOR_CMD=1
sudo setcap cap_net_admin+ep /usr/bin/nexutil

cd $NEXMON_ROOT/patches/bcm43455c0/7_45_189/
git clone https://github.com/seemoo-lab/nexmon_csi.git
```

`nexutil` links statically and emits `getaddrinfo`/`getprotobyname` warnings from
libnl - these are expected and harmless.

### Step 8 - firmware install, and two failures worth knowing about

```bash
cd $NEXMON_ROOT/patches/bcm43455c0/7_45_189/nexmon_csi
make -f Makefile.rpi install-firmware
```

This built cleanly. The ucode pipeline (DISASSEMBLING -> PATCHING -> ASSEMBLING
-> COMPRESSING) ran without trouble, which also settled the open question from
step 4: **`python2.7-minimal` was sufficient** - the reduced stdlib never became
a problem.

`install-firmware` copies the patched blob to `/lib/firmware/nexmon/` and points
`/lib/firmware/cypress/cyfmac43455-sdio.bin` at it via `update-alternatives`
(priority 30, manual mode). This is reversible - see `restore-wifi`.

**Failure 1 - `unmanage` aborts immediately.**

```
Error: Device 'wlan0' ... disconnecting failed: This device is not active
make: *** [Makefile.rpi:209: unmanage] Error 6
```

`nmcli dev disconnect wlan0` fails because `wlan0` was never connected - the
`wifis` section was removed from `network-config` at the very start of this
project. Because `make` stops at the first failing command, the target never
reaches its remaining steps, **including `rfkill unblock wifi`**.

**Failure 2 - `reload-full` then fails on RF-kill.**

```
SIOCSIFFLAGS: Operation not possible due to RF-kill
```

A direct consequence of failure 1. Fix by running the rest of `unmanage` by hand:

```bash
sudo nmcli dev set wlan0 managed no
sudo nmcli radio wifi off
sudo rfkill unblock wifi
```

Then `make -f Makefile.rpi reload-full` succeeds.

**Failure 3 - `reload-full` succeeds but does not actually reload the firmware.**

This one is silent and the most important to know about. `Makefile.rpi` cycles
the **`brcmfmac_wcc`** module, but on this system the chip is driven by
**`brcmfmac_cyw`**, and in either case the firmware is loaded by the *core*
`brcmfmac` module:

```
brcmfmac_wcc    12288  0
brcmfmac_cyw    12288  0
brcmfmac       376832  2 brcmfmac_cyw,brcmfmac_wcc
```

Cycling only `_wcc` leaves the SDIO device attached, so no firmware re-download
happens. `make` still reports success. The giveaway is `dmesg`: no new
`brcmf_c_preinit_dcmds: Firmware:` line appears.

Reload the whole stack instead:

```bash
sudo modprobe -r brcmfmac_wcc; sudo modprobe -r brcmfmac_cyw; sudo modprobe -r brcmfmac
sudo modprobe brcmfmac
```

**Always verify by firmware version string, never by make's exit code:**

```
before: version 7.45.265 (28bca26 CY) FWID 01-b677b91b
after:  version 7.45.189 (nexmon.org/csi: a975-1)
```

### Step 9 - CSI configuration

`makecsiparams` must be built separately. Its `make install` fails looking for
`libs/armeabi/makecsiparams` (a cross-compile path that does not exist in a
native 64-bit build); install the binary that `make` produced instead:

```bash
cd $NEXMON_ROOT/patches/bcm43455c0/7_45_189/nexmon_csi/utils/makecsiparams
make
sudo install -m 755 makecsiparams /usr/local/bin/makecsiparams
sudo ln -sf /usr/local/bin/makecsiparams /usr/local/bin/mcp
```

**Do not use `iw dev wlan0 interface add mon0 type monitor`.** It fails with
`Operation not supported (-95)`, and it is the wrong approach for this workflow:
the driver is unaware of the chip's monitor state, so monitor mode is set on the
chip directly with `nexutil -m1`.

```bash
PARAMS=$(makecsiparams -c 1/20 -C 1 -N 1)
sudo ip link set wlan0 up
sudo nexutil -Iwlan0 -s500 -b -l34 -v"$PARAMS"
sudo nexutil -Iwlan0 -m1
sudo nexutil -Iwlan0 -m          # confirm -> "monitor: 1"
```

## Verified working

```
$ sudo tcpdump -i wlan0 dst port 5500 -c 15 -n
18:15:16.457406 IP 10.10.10.10.5500 > 255.255.255.255.5500: UDP, length 274
18:15:16.457607 IP 10.10.10.10.5500 > 255.255.255.255.5500: UDP, length 274
...
15 packets captured
```

CSI frames arrive as 274-byte UDP datagrams from `10.10.10.10:5500` broadcast to
`255.255.255.255:5500`. The source address is synthetic - generated by the
patched firmware's UDP tunnel, not a real host.

## Persistence across reboots

| Survives reboot | Does not survive reboot |
|---|---|
| Patched firmware (`update-alternatives`) | `nexutil` CSI parameters |
| `makecsiparams`, `nexutil` binaries | `nexutil -m1` monitor flag |
| `/usr/local/bin/csi-enable` | `wlan0` unmanaged state |

Re-arm after any reboot with:

```bash
csi-enable 1/20          # or: csi-enable 36/80 1 1
```

That script lives on the Pi at `/usr/local/bin/csi-enable`. There is no
host-side copy — `bin/csi-sniff` applies the same parameters over SSH.

## Reverting to stock Wi-Fi

```bash
cd $NEXMON_ROOT/patches/bcm43455c0/7_45_189/nexmon_csi
make -f Makefile.rpi restore-wifi
# or directly:
sudo update-alternatives --auto cyfmac43455-sdio.bin
# then reload the full module stack and confirm dmesg reports 7.45.265
```

## Expected outcome

Once complete, CSI extraction is configured with `nexutil` and `wlan0` is placed
in monitor mode. CSI frames are then read off the interface — commonly with
`tcpdump` on UDP port 5500.

## References

- [seemoo-lab/nexmon_csi](https://github.com/seemoo-lab/nexmon_csi)
- [seemoo-lab/nexmon](https://github.com/seemoo-lab/nexmon)
- [Discussion #395 — recent kernels / Makefile.rpi](https://github.com/seemoo-lab/nexmon_csi/discussions/395)
- [Discussion #605 — firmware 7.45.241 unsupported](https://github.com/seemoo-lab/nexmon/discussions/605)


---

# 10. Payload validation and reboot persistence

## Reboot persistence — confirmed by accident

The Pi was power-cycled between sessions (~23 hours). On the next boot, with no
intervention:

```
[11.235247] brcmfmac: brcmf_c_preinit_dcmds: Firmware: BCM4345/6 wl0:
            Aug 26 2026 18:11:17 version 7.45.189 (nexmon.org/csi: a975-1)

update-alternatives: Status: manual
                     Value:  /lib/firmware/nexmon/brcmfmac43455-sdio.bin
```

The patched firmware loaded automatically. `monitor: 0` and `wlan0 DOWN`, exactly
as the persistence table predicts. `csi-enable 1/20` restored collection in one
command.

So the patched firmware survives a **full power cycle**, not merely a warm
reboot.

> Note: the journal is volatile on this image (`Storage=auto`, no
> `/var/log/journal`), so previous-boot logs do not survive. If you need to
> diagnose a crash after the fact, enable persistent logging first:
> `sudo mkdir -p /var/log/journal && sudo systemd-journald --flush`

## The real packet layout

The layout commonly quoted (a 4-byte `0x11111111` magic) is **wrong** for this
build. Confirmed by hexdump of a live capture:

```
11 11 | be | 80 | 04 cd c0 83 c2 62 | b0 e6 | 00 00 | 01 10 | 65 00 | a4 ee ...
magic  RSSI  FC   source MAC          seq     core     chanspec chipver  CSI
```

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | magic `0x1111` |
| 2 | 1 | RSSI, signed dBm |
| 3 | 1 | frame control |
| 4 | 6 | source MAC |
| 10 | 2 | sequence counter |
| 12 | 2 | core / spatial-stream id |
| 14 | 2 | chanspec |
| 16 | 2 | chip version |
| 18 | N*4 | CSI, N int16 pairs (imag, real), little-endian |

## Two traps when writing a parser

**1. Do not derive the subcarrier count from the payload length.** Most frames
are 274 bytes (18 + 64*4), but some arrive at **278 bytes** with 4 trailing bytes
past the CSI block. Deriving `N = len/4` yields a bogus 65 subcarriers for those.
Derive `N` from the chanspec bandwidth field instead:

```python
bw = chanspec & 0x3800          # 0x1000=20MHz, 0x1800=40, 0x2000=80
nsub = {0x1000: 64, 0x1800: 128, 0x2000: 256}[bw]
```

**2. Subcarrier 0 is not a measurement.** It was byte-identical (`a4ee8a05`) in
all 60 captured frames, across four different transmitters. It is a fixed
firmware value — discard it. The DC/guard region near the band centre
(subcarriers ~24–39 at 20 MHz) also carries large artifact values and is
normally discarded too.

## Validation results

Decoded with `csitools/` (no external dependencies):

```
UDP packets examined : 60
valid CSI frames     : 60
bad magic            : 0
subcarriers per frame: {64: 60}
distinct source MACs : 4
VERDICT: 60/60 frames parsed with correct magic and consistent structure.
```

Field values are physically plausible: RSSI −65/−66 dBm, chanspec `0x1001`
(channel 1 / 20 MHz, matching the configuration), and four distinct
transmitters — three of them consecutive BSSIDs on a single AP radio.

Two checks confirm the CSI is a real channel measurement rather than a fixed
pattern:

| Check | Result | Interpretation |
|---|---|---|
| Subcarrier 10 magnitude across 37 frames from one AP | 780–1140, σ = 104.8 | **varying** — real channel dynamics |
| Median adjacent-subcarrier jump / median magnitude | **0.13** | **smooth** — frequency-selective response, not noise (noise would be ≈1.0) |

## Using the decoder

```bash
# capture on the Pi (classic pcap, not pcapng)
ssh pi4b-nexmon 'sudo timeout 25 tcpdump -i wlan0 dst port 5500 -c 60 -w /tmp/csi.pcap'
scp pi4b-nexmon:/tmp/csi.pcap ./

# decode on this PC
python3 -c "import sys; sys.path.insert(0,'lib'); import csi_io; print(csi_io.load('csi.pcap')[0].shape)"
```

Sample captures are in `data/reference/`, and `bin/csi-regress` checks the
decode pipeline against them.

> **Superseded:** these figures were measured by sniffing beacons, which give
> ~10x more variable CSI than data frames. See `docs/10-collection-method.md` for
> the validated collection method.


---

# 11. Using a controlled transmitter

## Where ambient CSI comes from

With no MAC filter, CSI is measured from **every** frame the chip overhears on
the configured channel - no association required, no router of your own needed.
In an initial 60-frame capture on channel 1 the sources were:

```
 35  management  Probe Response
 18  management  Beacon
  4  control
  2  management  Action
  1  data
```

from four transmitters, three of them consecutive BSSIDs of a single campus AP
(`04:cd:c0:83:c2:61/62/63`, SSID `WiFi@OSU`, confirmed by scanning from the PC).
Every AP beacons roughly every 100 ms regardless of client activity, so the air
is never silent - that alone yields ~10 CSI samples/s per AP for free.

The drawback is that none of it is under your control: transmitters move, power
levels change, and probe-response volume tracks how many phones are nearby.

## Locking onto one transmitter

`makecsiparams -m` filters on source MAC (up to four, comma-separated):

```bash
csi-enable 149/20 1 1 66:D8:D6:E3:5F:D4
```

Measured with a phone hotspot as the transmitter:

| | Ambient (ch 1) | Hotspot, filtered (ch 149) |
|---|---|---|
| Distinct source MACs | 4 | **1** |
| RSSI | -66 dBm | **-34 dBm** |
| Valid frames | 60/60 | 40/40 |
| Rate | irregular | **10.0 frames/s** |
| Median inter-frame gap | - | **102.4 ms** |

102.4 ms is exactly the 802.11 beacon interval (100 TU x 1024 us), with an
observed spread of only 101.4-103.3 ms - a very stable clock to sample against.

## Practical notes

**Match the band.** A phone hotspot may land on 5 GHz (this one chose channel
149). CSI configured for channel 1 will see nothing from it. Check the
transmitter's actual channel first - `nmcli dev wifi list` from the PC is an
easy way, and it does not disturb the Pi's monitor mode.

**iPhone hotspots sleep.** iOS shuts the hotspot down after roughly 90 seconds
with no client associated, and beacons stop. Keep a device connected (or the
Personal Hotspot settings screen open) for the duration of a capture.

**Beacons give 10 Hz; sensing usually wants more.** For higher rates, associate a
client to the hotspot and generate traffic *that the hotspot transmits* - the
MAC filter only matches frames sent **from** that address, so a client pinging
the hotspot works (the replies come from the hotspot), while traffic flowing the
other way does not.

**Wider bandwidth = finer frequency resolution.** `149/80` yields 256
subcarriers instead of 64. Beacons are normally sent at 20 MHz for
compatibility, so a wide capture is most useful with data traffic rather than
beacons alone.

**No password is needed.** Monitor mode never associates, so CSI can be measured
from any transmitter without its credentials.
