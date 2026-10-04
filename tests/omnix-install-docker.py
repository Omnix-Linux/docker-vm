#!/usr/bin/env python3
"""Real opt-in ISO -> installation -> same-VM reboot test.

uv run --with pexpect python tests/omnix-install-docker.py ISO [FLAVOR]
Uses the shipping Docker image/Compose file, not a separate QEMU configuration.
Artifacts remain in the printed workspace directory; only its project is removed.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
import pexpect

ROOT = Path(__file__).resolve().parents[1]
iso = Path(sys.argv[1]).resolve()
flavor = sys.argv[2] if len(sys.argv) > 2 else "atrium"
if flavor not in {"atrium", "autarchy-stable", "autarchy-latest", "minimal"}:
    sys.exit("Unknown flavor")
if not iso.is_file():
    sys.exit("ISO does not exist")
project = "omnix-test-" + uuid.uuid4().hex
runtime = Path(os.environ["XDG_RUNTIME_DIR"]) / project
runtime.mkdir(mode=0o700)
secret = runtime / "vnc-password"
secret.write_text(secrets.token_urlsafe(24))
secret.chmod(0o600)
artifacts = ROOT.parent / ".omnix-demo-tests" / project
artifacts.mkdir(parents=True)
env = dict(os.environ, SESSION_RUNTIME_DIR=str(runtime), SESSION_UID=str(os.getuid()),
           SESSION_GID=str(os.getgid()), OMNIX_KVM_GID=str(Path('/dev/kvm').stat().st_gid),
           OMNIX_ISO_PATH=str(iso))
compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.omnix.yaml")]

def run(*args, **kw):
    return subprocess.run(args, check=True, env=env, cwd=ROOT, **kw)

def qmp(request):
    code = """import socket,json,sys
s=socket.socket(socket.AF_UNIX);s.connect('/tmp/omnix-qmp.sock');f=s.makefile('rwb');f.readline()
for command in [{'execute':'qmp_capabilities'},json.loads(sys.argv[1])]:
 f.write(json.dumps(command).encode()+b'\\n');f.flush()
 while True:
  r=json.loads(f.readline())
  if 'event' in r: continue
  if 'error' in r: raise RuntimeError(r['error'])
  if 'return' in r: break
print(json.dumps(r))
"""
    run("docker", "exec", container, "python3", "-c", code, json.dumps(request))

print(f"ARTIFACTS {artifacts}", flush=True)
console = None
try:
    run(*compose, "up", "-d", "--build")
    container = subprocess.check_output([*compose, "ps", "-q", "desktop"], env=env, cwd=ROOT, text=True).strip()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        health = subprocess.check_output(["docker", "inspect", "-f", "{{.State.Health.Status}}", container], text=True).strip()
        if health == "healthy": break
        time.sleep(1)
    else: raise RuntimeError("VM never became healthy")
    # Attach to the private serial socket, with no published port or host device.
    code = """import socket,select,os
s=socket.socket(socket.AF_UNIX);s.connect('/work/session/console.sock')
while True:
 for source in select.select([s,0],[],[])[0]:
  data=s.recv(65536) if source is s else os.read(0,65536)
  if not data: raise SystemExit(0)
  if source is s: os.write(1,data)
  else: s.sendall(data)
"""
    log = (artifacts / "install.log").open("w")
    console = pexpect.spawn("docker", ["exec", "-i", container, "python3", "-u", "-c", code],
                            encoding="utf-8", codec_errors="replace", timeout=600, searchwindowsize=8192, logfile=log)
    # Login banner may precede attachment; Enter elicits a fresh prompt.
    console.sendline("")
    console.expect(r"nixos@nixos:.*\$", timeout=600)
    print("LIVE_ISO_BOOTED", flush=True)
    qmp({"execute":"screendump", "arguments":{"filename":"/work/session/live.ppm"}})
    run("docker", "cp", f"{container}:/work/session/live.ppm", str(artifacts / "live.ppm"))
    answers = (f"OMNIX_DISK=/dev/vda OMNIX_FS=btrfs OMNIX_LUKS=0 OMNIX_FLAVOR={flavor} "
               "OMNIX_USER=tester OMNIX_PASSWORD=tester OMNIX_HOSTNAME=omnixtest "
               "OMNIX_TIMEZONE=UTC OMNIX_YES=1")
    console.sendline(f"sudo {answers} omnix-install; printf '\\nINSTALL_RC=%s\\n' $?")
    console.expect(r"\r*\nINSTALL_RC=(\d+)\r*\n", timeout=7200)
    if console.match.group(1) != "0": raise RuntimeError("Installer failed; see install.log")
    print("INSTALL_COMPLETED", flush=True)
    console.sendline("sudo test -e /mnt/etc/nixos/flake.lock && sudo test -e /mnt/boot/EFI/BOOT/BOOTX64.EFI && printf '\\nLAYOUT_OK\\n'")
    console.expect(r"\r*\nLAYOUT_OK\r*\n", timeout=60)
    console.sendline("sync; sudo reboot")
    # Installed desktop does not expose a serial getty; inspect actual framebuffer.
    time.sleep(90)
    qmp({"execute":"screendump", "arguments":{"filename":"/work/session/installed.ppm"}})
    run("docker", "cp", f"{container}:/work/session/installed.ppm", str(artifacts / "installed.ppm"))
    print("REBOOT_SCREENSHOT_READY (inspect installed.ppm to verify desktop)", flush=True)
finally:
    if console: console.close(force=True)
    run(*compose, "down", "--remove-orphans", "--volumes")
    # Runtime directory contains test-only secret: use session-authorized trash tool.
    subprocess.run(["safe-rm", "-r", str(runtime)], check=False)
