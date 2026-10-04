# Try Omnix

This fork adds a native desktop viewer for the **real Omnix installer**. Docker
runs a KVM-accelerated QEMU guest, rather than pretending that a container is a
bootable operating system. The same viewer covers booting the ISO, choosing a
flavor, installing, rebooting, and using the installed desktop.

## Launch

On an x86-64 Linux host with Docker, accessible `/dev/kvm`, and a graphical
session:

```sh
git submodule update --init --recursive
nix build '.?submodules=1#docker-vm'
./result/bin/omnix-demo
```

The package also installs a **Try Omnix** desktop entry. The launcher downloads
the official Omnix 0.1.1 ISO once and verifies its SHA-256 before use. Later
launches reuse the verified copy in `$XDG_CACHE_HOME/omnix-demo` (normally
`~/.cache/omnix-demo`). A local ISO can be supplied with `--iso /path/to/omnix.iso`.
The Docker image is built locally on first launch.

The guest receives four virtual CPUs, 6 GiB RAM and a blank 40 GiB virtual disk.
Allow at least 8 GiB of available host RAM plus room for the desktop viewer,
ISO, Docker image, and installed guest. This initial version requires native
Linux/KVM; macOS and Windows launchers are not implemented.

## Install and try

At the live ISO prompt, run `sudo omnix-install`. Its real terminal interface
asks for the virtual disk (`/dev/vda`), filesystem, encryption, desktop flavor,
and user details. Atrium selects KDE Plasma; Autarchy selects the Omarchy port.
These are the upstream installer's choices, not a simulated installation.

When installation finishes, run `sudo reboot`. The VM boots its installed disk
on subsequent boots, keeping the viewer connected. Log in using the account
you created and try the desktop.

**Keep the viewer open while testing.** Closing it removes its container and
its virtual disk. Every launch is a fresh installation session. The downloaded
ISO and Docker image remain cached. Disk persistence and resuming sessions are
not currently provided.

## Isolation

Only the ISO and a private runtime directory are bound into the container.
The writable guest disk is a project-scoped Docker volume; host disks, home,
and the Docker socket are not mounted. `/dev/kvm` provides virtualization.
Networking is QEMU user networking with outbound Internet access for packages.
VNC is password protected, has no published host port, and reaches the native
viewer through its authenticated local bridge.

Unlike the original private Chromium mode, the Omnix guest uses disk-backed
storage during the session. The original mode remains available as `docker-vm`
and retains its separate tmpfs requirements.

## Validation

The initial implementation was tested on native Linux/KVM with the official
0.1.1 ISO: Atrium installation finished with exit code 0, the installed flake
lock and UEFI bootloader existed, the same VM rebooted into SDDM, and the
created user logged into KDE Plasma. Authenticated VNC keyboard input and
framebuffer capture were checked. The packaged native app was also launched
and closed normally, verifying removal of its container and disk volume.
Autarchy is available through the real installer menu; its desktop has not
yet been validated in this Docker harness.

Run the opt-in installation harness (it downloads guest packages):

```sh
uv run --with pexpect python tests/omnix-install-docker.py /path/to/omnix.iso atrium
```

It checks installer completion and boot files, reboots, and saves a framebuffer
capture for inspection. It does not automatically assert desktop login.
`bash tests/validation.sh` covers the viewer behavior, guest command, and
Compose configuration; the Nix package build runs the native Rust checks.
