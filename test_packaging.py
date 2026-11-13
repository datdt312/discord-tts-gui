"""Build and inspect a real Linux package without installing on the host."""
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('dpkg-deb'),
                     'Linux and dpkg-deb required for package integration')
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='tts package tests ')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.work = Path(cls.directory.name)
        result = subprocess.run([sys.executable, str(ROOT / 'packaging/build_deb.py'),
                                 '--output-dir', str(cls.work)],
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError('Package build failed:\n' + result.stdout + result.stderr)
        packages = list(cls.work.glob('discord-tts-gui_*_all.deb'))
        if len(packages) != 1:
            raise AssertionError('Expected exactly one installer from the build')
        cls.package = packages[0]
        cls.extracted = cls.work / 'extracted'
        subprocess.run(['dpkg-deb', '-x', str(cls.package), str(cls.extracted)], check=True)
        cls.appdir = cls.extracted / 'usr/share/discord-tts-gui'

    def test_dependencies_install_native_runtime_without_pip(self):
        result = subprocess.run(['dpkg-deb', '-f', str(self.package), 'Architecture', 'Depends'],
                                check=True, text=True, capture_output=True)
        self.assertIn('all', result.stdout)
        for dependency in ('python3 (>= 3.10)', 'python3-tk', 'python3-aiohttp',
                           'python3-pyqt6 | python3-pyqt5', 'python3-venv', 'libsndfile1',
                           'ffmpeg', 'pulseaudio-utils', 'espeak-ng', 'xauth'):
            self.assertIn(dependency, result.stdout)
        self.assertNotIn('pip', result.stdout)

    def test_contains_current_app_and_portable_python_sources(self):
        self.assertEqual((self.appdir / 'app.py').read_bytes(), (ROOT / 'app.py').read_bytes())
        for name in ('neural_backend.py', 'neural_runtime.py', 'neural_playback.py',
                     'neural_model_files.py', 'desktop_ui.py', 'qt_ui.py',
                     'runtime_support.py', 'media_tools.py', 'portable_audio.py',
                     'portable_playback.py'):
            self.assertEqual((self.appdir / name).read_bytes(), (ROOT / name).read_bytes())
        for relative in ('edge_tts/__init__.py', 'edge_tts/drm.py', 'certifi/cacert.pem',
                         'tabulate/__init__.py', 'typing_extensions.py'):
            self.assertTrue((self.appdir / 'vendor' / relative).is_file(), relative)
        for path in self.extracted.rglob('*'):
            self.assertNotIn(path.name, ('.venv', '__pycache__', '.git'))
            self.assertFalse(path.suffix in ('.so', '.pyc'), str(path))

    def test_bundled_dependencies_import_without_development_environment(self):
        script = (
            'import json, sys\n'
            'sys.path.insert(0, sys.argv[1])\n'
            'import certifi, tabulate, typing_extensions\n'
            'from pathlib import Path\n'
            'assert Path(certifi.where()).is_file()\n'
            'assert hasattr(typing_extensions, "NotRequired")\n'
            'assert hasattr(typing_extensions, "Unpack")\n'
            'print(json.dumps([certifi.__file__, tabulate.__file__, typing_extensions.__file__]))\n')
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', script,
                                 str(self.appdir / 'vendor')],
                                check=True, text=True, capture_output=True, timeout=10)
        self.assertTrue(all(str(self.appdir / 'vendor') in path
                            for path in json.loads(result.stdout)))

    def test_desktop_launcher_resolves_to_packaged_executable_and_icon(self):
        desktop = self.extracted / 'usr/share/applications/discord-tts-gui-packaged.desktop'
        properties = dict(line.split('=', 1) for line in desktop.read_text().splitlines()
                          if '=' in line)
        self.assertEqual(properties['Exec'], '/usr/bin/discord-tts-gui')
        self.assertEqual(properties['Terminal'], 'false')
        self.assertEqual(properties['Name'], 'Discord TTS GUI (Linux)')
        self.assertTrue(os.access(self.extracted / 'usr/bin/discord-tts-gui', os.X_OK))
        self.assertTrue((self.extracted / 'usr/share/icons/hicolor/scalable/apps' /
                         (properties['Icon'] + '.svg')).is_file())
        if shutil.which('desktop-file-validate'):
            subprocess.run(['desktop-file-validate', str(desktop)], check=True)

    def test_includes_dependency_licenses_and_vietnamese_instructions(self):
        documentation = self.extracted / 'usr/share/doc/discord-tts-gui'
        for relative in ('README.vi.txt', 'copyright', 'licenses/edge-tts-LICENSE',
                         'licenses/certifi-LICENSE', 'licenses/tabulate-LICENSE',
                         'licenses/typing_extensions-LICENSE', 'licenses/GPL-3'):
            self.assertTrue((documentation / relative).is_file(), relative)
        self.assertIn('Kubuntu', (documentation / 'README.vi.txt').read_text())

    def test_relocated_launcher_reports_missing_dependencies_without_tk_window(self):
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(self.appdir / 'launcher.py'),
                                 '--check'], text=True, capture_output=True, timeout=10)
        self.assertIn(result.returncode, (0, 1))
        self.assertNotIn('Traceback', result.stderr)
        if result.returncode:
            self.assertIn('python3-aiohttp', result.stderr)
            self.assertIn('apt', result.stderr)
        else:
            self.assertIn('7.3.1', result.stdout)

    def test_shipped_python_syntax_is_compatible_with_python_310(self):
        for source in self.appdir.rglob('*.py'):
            with self.subTest(source=source.relative_to(self.appdir)):
                ast.parse(source.read_text(encoding='utf-8'), filename=str(source),
                          feature_version=(3, 10))

    @unittest.skipUnless(importlib.util.find_spec('PyQt6') or importlib.util.find_spec('PyQt5'),
                         'Qt required for packaged GUI smoke test')
    def test_extracted_package_starts_qt_default_and_closes_cleanly(self):
        script = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / 'vendor'))
import qt_ui
import app
app.pulse_list = lambda kind: []
def show_and_close(root):
    root.window.show()
    root.application.processEvents()
    assert root.window.isVisible()
    assert root.window.width() == 820
    root.window.close()
    root.application.processEvents()
    assert root._destroyed
    print(qt_ui.QT_BINDING + ': shown and closed')
    return 0
qt_ui.QtRoot.mainloop = show_and_close
raise SystemExit(app.main())
'''
        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', script,
                                 str(self.appdir)], env=environment, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shown and closed', result.stdout)


if __name__ == '__main__':
    unittest.main()
