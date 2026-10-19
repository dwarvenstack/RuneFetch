"""Verify installer handoff without launching an installer or quitting Python."""
import io
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from core import updater


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def file(self,name):
        path=self.root/name;path.write_bytes(b'test');return str(path)
    def test_missing_installer_rejected(self):
        self.assertFalse(updater.install_and_restart(str(self.root/'missing.exe')))
    def test_source_mode_never_installs(self):
        with patch.object(updater.sys,'frozen',False,create=True),patch.object(updater,'_reveal') as reveal,patch.object(updater.subprocess,'Popen') as launch:
            path=self.file('setup.exe');self.assertFalse(updater.install_and_restart(path))
            reveal.assert_called_once_with(path);launch.assert_not_called()
    def test_zip_is_revealed_instead_of_executed(self):
        with patch.object(updater,'_reveal') as reveal,patch.object(updater.subprocess,'Popen') as launch:
            path=self.file('portable.zip');self.assertFalse(updater.install_and_restart(path))
            reveal.assert_called_once_with(path);launch.assert_not_called()
    def test_failed_launch_does_not_quit(self):
        with patch.object(updater.sys,'frozen',True,create=True),patch.object(updater.subprocess,'Popen',side_effect=OSError('blocked')),patch.object(updater.threading,'Thread') as thread:
            self.assertFalse(updater.install_and_restart(self.file('setup.exe')))
            thread.assert_not_called()
    def test_frozen_build_launches_detached_installer(self):
        with patch.object(updater.sys,'frozen',True,create=True),patch.object(updater.subprocess,'Popen') as launch,patch.object(updater.threading,'Thread') as thread:
            path=self.file('setup.exe');self.assertTrue(updater.install_and_restart(path))
            args=launch.call_args.args[0]
            self.assertEqual(args[0],path);self.assertIn('/SILENT',args);self.assertIn('/CLOSEAPPLICATIONS',args)
            self.assertEqual(launch.call_args.kwargs['creationflags'],0x208)
            thread.return_value.start.assert_called_once()


if __name__=='__main__': unittest.main()
