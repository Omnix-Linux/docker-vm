#!/usr/bin/env python3
"""Boot the real installer ISO on a private virtual disk; expose authenticated RFB."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time


def command(iso, work, *, kvm):
    iso, work = Path(iso), Path(work)
    if not iso.is_file():
        raise ValueError("Omnix installer ISO is missing")
    if not work.is_dir() or any(c in str(work) + str(iso) for c in ",\n\r\0"):
        raise ValueError("Guest paths must be directories/files without QEMU option separators")
    return [
        "qemu-system-x86_64", "-name", "Omnix demo", "-accel", "kvm" if kvm else "tcg",
        "-cpu", "host" if kvm else "max", "-m", "6144", "-smp", "4",
        "-drive", f"file={work / 'guest.qcow2'},format=qcow2,if=virtio",
        "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
        "-drive", f"if=pflash,format=raw,file={work / 'uefi-vars.fd'}",
        "-cdrom", str(iso), "-boot", "order=c,once=d,menu=on",
        "-nic", "user,model=virtio-net-pci", "-device", "virtio-vga",
        "-device", "qemu-xhci", "-device", "usb-tablet",
        "-display", "none", "-vnc", "0.0.0.0:0,password=on",
        "-qmp", "unix:/tmp/omnix-qmp.sock,server=on,wait=off",
        "-chardev", f"socket,id=console,path={work / 'console.sock'},server=on,wait=off,logfile={work / 'serial.log'}",
        "-serial", "chardev:console",
    ]


def password_command(password):
    return {"execute": "set_password", "arguments": {"protocol": "vnc", "password": password}}


def authenticate(process, password):
    deadline = time.monotonic() + 30
    while not Path("/tmp/omnix-qmp.sock").exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("QEMU did not start its control socket")
        time.sleep(.05)
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(10)
        client.connect("/tmp/omnix-qmp.sock")
        stream = client.makefile("rwb")
        json.loads(stream.readline())  # QMP greeting
        for request in [{"execute": "qmp_capabilities"}, password_command(password)]:
            stream.write(json.dumps(request).encode() + b"\n")
            stream.flush()
            while True:
                reply = json.loads(stream.readline())
                if "event" in reply:
                    continue
                if "error" in reply:
                    raise RuntimeError("QEMU rejected VNC setup")
                if "return" in reply:
                    break
    Path("/tmp/omnix-ready").touch()


def main():
    work = Path("/work/session")
    work.mkdir(mode=0o700)
    password = Path("/run/session/vnc-password").read_text().strip()
    if not password:
        raise ValueError("VNC password is required")
    args = command("/installer/omnix.iso", work, kvm=os.access("/dev/kvm", os.R_OK | os.W_OK))
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(work / "guest.qcow2"), "40G"], check=True)
    shutil.copyfile("/usr/share/OVMF/OVMF_VARS_4M.fd", work / "uefi-vars.fd")
    process = subprocess.Popen(args)

    def stop(_signal, _frame):
        process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        authenticate(process, password)
        return process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
