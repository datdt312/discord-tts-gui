"""Platform paths do not create directories or require platform packages."""
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class RuntimeSupportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('runtime_support'))
        self.module = importlib.import_module('runtime_support')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.enterContext(patch('pathlib.Path.home', return_value=self.home))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def test_linux_preserves_existing_xdg_data_and_state_locations(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.home / 'data'),
                                     'XDG_STATE_HOME': str(self.home / 'state')}):
            self.assertEqual(self.module.user_data_dir(system='Linux'), self.home / 'data/discord-tts-gui')
            self.assertEqual(self.module.user_state_dir(system='Linux'), self.home / 'state/discord-tts-gui')

    def test_linux_ignores_relative_or_empty_xdg_overrides(self):
        for override in ('', 'relative'):
            with patch.dict(os.environ, {'XDG_DATA_HOME': override, 'XDG_STATE_HOME': override}):
                self.assertEqual(self.module.user_data_dir(system='Linux'), self.home / '.local/share/discord-tts-gui')
                self.assertEqual(self.module.user_state_dir(system='Linux'), self.home / '.local/state/discord-tts-gui')
        self.assertFalse((self.home / '.local').exists())

    def test_windows_keeps_runtime_and_logs_in_local_appdata(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.home / 'Local')}):
            self.assertEqual(self.module.user_data_dir(system='Windows'), self.home / 'Local/discord-tts-gui')
            self.assertEqual(self.module.user_state_dir(system='Windows'), self.home / 'Local/discord-tts-gui')
        self.assertEqual(self.module.user_data_dir('custom', system='Windows'), self.home / 'AppData/Local/custom')

    def test_macos_uses_application_support_and_logs(self):
        self.assertEqual(self.module.user_data_dir(system='Darwin'), self.home / 'Library/Application Support/discord-tts-gui')
        self.assertEqual(self.module.user_state_dir(system='Darwin'), self.home / 'Library/Logs/discord-tts-gui')

    def test_private_interpreter_uses_platform_venv_layout(self):
        self.assertEqual(self.module.venv_python(self.home, system='Windows'), self.home / 'Scripts/python.exe')
        for system in ('Linux', 'Darwin'):
            self.assertEqual(self.module.venv_python(self.home, system=system), self.home / 'bin/python')


if __name__ == '__main__':
    unittest.main()
