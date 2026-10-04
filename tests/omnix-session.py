"""Command/lifecycle checks for the disposable Omnix guest (no host disk access)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("omnix_session", ROOT / "images/omnix/session.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GuestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.iso = self.root / "installer with spaces.iso"
        self.iso.write_bytes(b"test ISO")
        self.work = self.root / "work"
        self.work.mkdir()

    def test_installs_to_virtual_disk_and_reboots_from_it(self):
        args = module.command(self.iso, self.work, kvm=True)
        self.assertIn("order=c,once=d,menu=on", args)
        self.assertIn(str(self.iso), args)
        self.assertIn("kvm", args)
        self.assertIn("host", args)
        disk = args[args.index("-drive") + 1]
        self.assertIn(str(self.work / "guest.qcow2"), disk)
        self.assertIn("format=qcow2", disk)
        self.assertIn("if=virtio", disk)
        self.assertFalse(any("/dev/sd" in arg or "/dev/nvme" in arg for arg in args))
        self.assertNotIn("-no-reboot", args)

    def test_software_fallback_and_network_isolation(self):
        args = module.command(self.iso, self.work, kvm=False)
        self.assertIn("tcg", args)
        self.assertNotIn("host", args)
        self.assertIn("user,model=virtio-net-pci", args)
        self.assertNotIn("hostfwd", " ".join(args))
        self.assertIn("password=on", " ".join(args))
        self.assertNotIn("-monitor", args)

    def test_rejects_missing_iso_and_unsafe_drive_path(self):
        with self.assertRaises(ValueError):
            module.command(self.root / "missing.iso", self.work, kvm=True)
        unsafe = self.root / "comma,path"
        unsafe.mkdir()
        with self.assertRaises(ValueError):
            module.command(self.iso, unsafe, kvm=True)

    def test_password_is_sent_over_qmp_not_process_arguments(self):
        payload = module.password_command("private-secret-value")
        self.assertEqual(payload["execute"], "set_password")
        self.assertEqual(payload["arguments"]["protocol"], "vnc")
        self.assertEqual(payload["arguments"]["password"], "private-secret-value")
        self.assertNotIn("private-secret-value", " ".join(module.command(self.iso, self.work, kvm=True)))


if __name__ == "__main__":
    unittest.main()
