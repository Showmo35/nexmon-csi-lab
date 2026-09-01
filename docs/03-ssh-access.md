# 3. SSH access

## The problem

The image's `user-data` authorised a public key whose **private half lives on a
different computer**. Combined with `ssh_pwauth: false` (password auth disabled),
the Pi would have been unreachable from this PC.

Two options existed:

- **(a)** Generate a new keypair here and edit `user-data` on the boot partition.
- **(b)** Copy the original private key over from the Windows PC.

**(a) was chosen** — self-contained, and it avoids moving private key material
between machines over USB sticks or cloud sync.

This works only because the Pi had **not yet booted**. `user-data` is consumed by
cloud-init on first boot; editing it beforehand is safe and is the intended
mechanism.

## Key generation

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pi4b_nexmon -N "" -C "showmik@showmik-HP-ProBook-440-G5-nexmon"
```

| | |
|---|---|
| Type | ed25519 |
| Private key | `~/.ssh/pi4b_nexmon` (mode 600) |
| Public key | `~/.ssh/pi4b_nexmon.pub` |
| Fingerprint | `SHA256:5XBaWiqFHa00KMlT0dwGD0J5hTdimmax1eo4Jb5BApk` |
| Passphrase | **none** |

The empty passphrase is deliberate — it allows unattended automation against the
Pi. The tradeoff is that anyone who obtains the file has immediate access, and
since the Pi also has passwordless sudo, that means root. Reconsider both if the
Pi leaves this isolated cable.

## The `user-data` edit

Exactly one line changed:

```diff
   ssh_authorized_keys:
-    - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMGTlet+ahNFE5+zhSA34kbwaxsm+cx/WKyDKd0S9FlE showmik@windows-pc-nexmon"
+    - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID2PTXkQH/GqKJLSqtQIn++c14WlQdvesQK2pawaXJOr showmik@showmik-HP-ProBook-440-G5-nexmon"
```

Everything else was left untouched: `hostname: pi4b-nexmon`, `name: nexmon`,
`enable_ssh: true`, `ssh_pwauth: false`.

The edit was verified three ways before ejecting the drive:

1. `diff` against a backup, showing one changed line
2. YAML re-parsed to confirm the file was still valid cloud-config
3. The key in `user-data` compared byte-for-byte with `~/.ssh/pi4b_nexmon.pub`

## SSH client config

`~/.ssh/config` (copy in `config/pc/ssh_config`):

```
Host pi4b-nexmon
    HostName 10.0.0.100
    User nexmon
    IdentityFile ~/.ssh/pi4b_nexmon
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new

Host pi4b-nexmon-mdns
    HostName pi4b-nexmon.local
    User nexmon
    IdentityFile ~/.ssh/pi4b_nexmon
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
```

Notes on the non-obvious options:

- `IdentitiesOnly yes` — without it, SSH offers every key the agent holds and can
  hit `MaxAuthTries` before reaching the right one.
- `StrictHostKeyChecking accept-new` — accepts the host key on first contact
  without an interactive prompt, but still refuses if a **known** host key later
  changes. This is what makes non-interactive automation possible. It does mean
  the very first connection is trust-on-first-use; on a direct cable with no
  third party present, that is a reasonable risk.

## Verification

```
$ ssh pi4b-nexmon "hostname && uname -a"
pi4b-nexmon
Linux pi4b-nexmon 6.18.34+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.18.34-1+rpt1 (2026-06-09) aarch64 GNU/Linux
```

Confirmed at the same time:

- user `nexmon`, uid 1000, member of `sudo`
- `cloud-init status: done`
- booted from `sda` with `TRAN=usb` — the USB drive, as intended
- root filesystem auto-expanded 5.5 GB → 57 GB

## First-boot timing

Budget **2–4 minutes**, not the 60–90 seconds one might expect. First boot runs
cloud-init, expands the root filesystem, generates SSH host keys, and
**typically reboots once** partway through.

During this project the Pi answered ping after ~6 s, then vanished again — that
was the self-reboot, not a failure. A useful pattern is to wait for *sustained*
reachability rather than a single successful ping:

```bash
# wait for 6 consecutive successful pings before declaring it up
streak=0
while [ $streak -lt 6 ]; do
  ping -c1 -W1 10.0.0.100 >/dev/null 2>&1 && streak=$((streak+1)) || streak=0
  sleep 5
done
```

## Passwordless sudo

Later enabled to allow an unattended Nexmon build:

```bash
echo "nexmon ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/010_nexmon-nopasswd
sudo chmod 440 /etc/sudoers.d/010_nexmon-nopasswd
```

Remove with `sudo rm /etc/sudoers.d/010_nexmon-nopasswd` once the build is done,
if you want password-required sudo back.
