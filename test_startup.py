"""Startup regressions; run with python3 -m unittest -v."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class InterpreterTests(unittest.TestCase):
    def test_system_python_restarts_in_app_venv_and_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            environment = folder / '.venv'
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(environment)],
                           check=True, capture_output=True, timeout=20)
            probe = folder / 'probe.py'
            probe.write_text(
                'import sys\n'
                f'sys.path.insert(0, {str(Path(app.__file__).parent)!r})\n'
                'import app\n'
                'app.__file__ = __file__\n'
                'app.use_app_venv()\n'
                'print(sys.prefix)\n'
                'print(sys.argv[1])\n', encoding='utf-8')
            result = subprocess.run([sys.executable, str(probe), 'argument with spaces'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(environment), 'argument with spaces'])

    def test_source_without_venv_continues_in_current_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / 'probe.py'
            probe.write_text(
                'import sys\n'
                f'sys.path.insert(0, {str(Path(app.__file__).parent)!r})\n'
                'import app\n'
                'app.__file__ = __file__\n'
                'app.use_app_venv()\n'
                'print(sys.prefix)\n', encoding='utf-8')
            result = subprocess.run([sys.executable, str(probe)], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), sys.prefix)


@unittest.skipUnless(shutil.which('xauth'), 'xauth is required for Xauthority fixtures')
class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.directory = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {
            'PATH': os.environ['PATH'],
            'HOME': str(self.directory),
            'XDG_RUNTIME_DIR': str(self.directory),
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def authority(self, name, display):
        path = self.directory / name
        path.touch(mode=0o600)
        subprocess.run(['xauth', '-f', str(path), 'add', display,
                        'MIT-MAGIC-COOKIE-1', '00' * 16],
                       check=True, capture_output=True)
        return path

    def test_preserves_explicit_display(self):
        os.environ['DISPLAY'] = ':23'
        app.restore_display()
        self.assertEqual(os.environ['DISPLAY'], ':23')

    def test_restores_local_display_from_session_authority(self):
        authority = self.authority('session.auth', socket.gethostname() + '/unix:7')
        os.environ['XAUTHORITY'] = str(authority)
        app.restore_display()
        self.assertEqual(os.environ.get('DISPLAY'), ':7')
        self.assertEqual(os.environ['XAUTHORITY'], str(authority))

    def test_finds_kde_authority_when_both_variables_are_missing(self):
        authority = self.authority('xauth_test', socket.gethostname() + '/unix:8')
        os.environ['DISPLAY'] = ''
        app.restore_display()
        self.assertEqual(os.environ.get('DISPLAY'), ':8')
        self.assertEqual(os.environ.get('XAUTHORITY'), str(authority))

    def test_does_not_guess_between_multiple_sessions(self):
        self.authority('xauth_first', socket.gethostname() + '/unix:7')
        self.authority('xauth_second', socket.gethostname() + '/unix:8')
        app.restore_display()
        self.assertNotIn('DISPLAY', os.environ)
        self.assertNotIn('XAUTHORITY', os.environ)

    def test_does_not_replace_explicit_unreadable_authority(self):
        os.environ['XAUTHORITY'] = str(self.directory / 'missing')
        self.authority('xauth_other', socket.gethostname() + '/unix:8')
        app.restore_display()
        self.assertNotIn('DISPLAY', os.environ)

    def test_no_authority_leaves_display_unset(self):
        app.restore_display()
        self.assertNotIn('DISPLAY', os.environ)


class StartupErrorTests(unittest.TestCase):
    def test_no_display_produces_actionable_error_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, DISPLAY='', WAYLAND_DISPLAY='', QT_QPA_PLATFORM='',
                               XAUTHORITY=directory + '/missing',
                               XDG_STATE_HOME=directory)
            result = subprocess.run(['python3', str(Path(app.__file__).resolve())],
                                    env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn('X11/XWayland', result.stderr)
            log = Path(directory) / 'discord-tts-gui' / 'startup.log'
            self.assertTrue(log.is_file(), 'A menu launch failure must leave a diagnostic log')
            self.assertIn('RuntimeError', log.read_text())


if __name__ == '__main__':
    unittest.main()
