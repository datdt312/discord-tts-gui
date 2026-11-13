"""Inspect native desktop recipes without requiring PyInstaller or downloads."""
import ast
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('desktop_builder', ROOT / 'packaging/build_desktop.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class DesktopPackagingTests(unittest.TestCase):
    def test_frozen_runtime_check_uses_bundled_resources_without_devices_or_models(self):
        spec = importlib.util.spec_from_file_location('desktop_entry', ROOT / 'packaging/desktop_entry.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work)
            uv = directory / 'tools' / ('uv.exe' if sys.platform == 'win32' else 'uv')
            uv.parent.mkdir()
            uv.write_bytes(b'not executed by check')
            ffmpeg = directory / 'ffmpeg'
            ffmpeg.write_bytes(b'not executed by check')
            (directory / 'workers').mkdir()
            for name in builder.WORKER_SOURCES:
                (directory / 'workers' / name).write_text('# worker')
            qt = types.ModuleType('PyQt6')
            widgets = types.ModuleType('PyQt6.QtWidgets')
            edge = types.SimpleNamespace(__version__='7.3.1')
            imageio = types.SimpleNamespace(get_ffmpeg_exe=lambda: str(ffmpeg))
            sound = mock.Mock(get_portaudio_version=mock.Mock(return_value=(1, 'test PortAudio')))
            modules = {'PyQt6': qt, 'PyQt6.QtWidgets': widgets, 'edge_tts': edge,
                       'imageio_ffmpeg': imageio, 'sounddevice': sound}
            with mock.patch.dict(sys.modules, modules), \
                    mock.patch.object(sys, 'frozen', True, create=True), \
                    mock.patch.object(sys, '_MEIPASS', str(directory), create=True):
                self.assertEqual(entry.check_bundle()['uv'], str(uv))
                sound.query_devices.assert_not_called()
                uv.unlink()
                with mock.patch.object(entry.shutil, 'which', return_value='/other/uv'):
                    with self.assertRaisesRegex(RuntimeError, 'Bundled uv executable is missing'):
                        entry.check_bundle()

    def test_plans_are_available_on_every_host_without_build_imports(self):
        for target, suffix in (('windows', '.zip'), ('macos', '.zip'), ('linux', '.tar.gz')):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='tts plan ') as work:
                result = subprocess.run([sys.executable, str(ROOT / 'packaging/build_desktop.py'),
                                         '--target', target, '--plan', '--output-dir', work],
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertEqual(plan['target'], target)
                self.assertTrue(plan['artifact'].endswith(suffix))
                self.assertIn('1.3.0', plan['artifact'])
                self.assertFalse(list(Path(work).iterdir()), 'planning must not build or download')

    def test_architecture_is_explicit_for_both_macos_builds(self):
        for machine, expected in (('AMD64', 'x86_64'), ('aarch64', 'arm64')):
            plan = builder.build_plan('macos', machine=machine)
            self.assertEqual(plan['architecture'], expected)
            command = plan['command']
            self.assertEqual(command[command.index('--target-architecture') + 1], expected)
            self.assertTrue(plan['bundle'].endswith('.app'))
            self.assertIn(expected, plan['artifact'])

    def test_each_bundle_has_modules_uv_ffmpeg_portaudio_and_external_workers(self):
        required = {'app', 'desktop_ui', 'qt_ui', 'neural_backend', 'neural_playback',
                    'neural_runtime', 'neural_model_files', 'runtime_support',
                    'media_tools', 'portable_audio', 'portable_playback'}
        for target in ('windows', 'macos', 'linux'):
            with self.subTest(target=target):
                plan = builder.build_plan(target)
                self.assertEqual(set(plan['modules']), required)
                command = plan['command']
                separator = ';' if target == 'windows' else ':'
                self.assertIn('<uv executable>' + separator + 'tools', command)
                for name in ('neural_runtime.py', 'neural_model_files.py'):
                    self.assertIn(str(ROOT / name) + separator + 'workers', command)
                    self.assertIn('workers/' + name, plan['worker_sources'])
                for package in ('PyQt6', 'imageio_ffmpeg', 'sounddevice'):
                    self.assertIn(package, command)
                if target != 'linux':
                    self.assertIn('_sounddevice_data', command)
                    self.assertIn('--windowed', command)
                self.assertIn('_sounddevice', command)
                self.assertIn('_cffi_backend', command)
                self.assertIn('PyQt5', plan['excluded'])
                self.assertIn('torch', plan['excluded'])
                self.assertNotIn('--onefile', command)

    def test_foreign_build_rejected_before_dependency_checks(self):
        foreign = 'macos' if builder.host_target() != 'macos' else 'windows'
        with mock.patch.object(builder, 'validate_build_environment') as dependencies:
            with self.assertRaisesRegex(RuntimeError, 'Native build required'):
                builder.build(foreign)
        dependencies.assert_not_called()

    def test_uv_is_located_from_package_without_running_it(self):
        with tempfile.TemporaryDirectory() as work:
            uv = Path(work) / 'uv.exe'
            uv.write_bytes(b'fake executable')
            fake_package = mock.Mock(find_uv_bin=mock.Mock(return_value=str(uv)))
            with mock.patch.dict(sys.modules, {'uv': fake_package}):
                self.assertEqual(builder.find_uv_binary(), uv.resolve())
            fake_package.find_uv_bin.assert_called_once_with()

    def test_build_inserts_actual_uv_binary_as_one_argument(self):
        with tempfile.TemporaryDirectory(prefix='tts native build ') as work:
            uv = Path(work) / 'tools with spaces' / 'uv'
            artifact = Path(work) / 'package.zip'
            with mock.patch.object(builder, 'validate_build_environment'), \
                    mock.patch.object(builder, 'find_uv_binary', return_value=uv), \
                    mock.patch.object(builder.subprocess, 'run') as run, \
                    mock.patch.object(builder, 'archive_bundle', return_value=artifact):
                self.assertEqual(builder.build(output_dir=work), artifact)
            command = run.call_args.args[0]
            separator = ';' if builder.host_target() == 'windows' else ':'
            self.assertIn(str(uv) + separator + 'tools', command)
            self.assertFalse(any('<uv executable>' in item for item in command))

    def test_archive_only_contains_bundle_and_explicit_documentation(self):
        with tempfile.TemporaryDirectory() as work:
            plan = builder.build_plan('windows', output_dir=work, machine='AMD64')
            bundle = Path(plan['bundle'])
            bundle.mkdir(parents=True)
            (bundle / 'Discord TTS GUI.exe').write_bytes(b'test only')
            (Path(work) / '.env').write_text('not an archive input')
            artifact = builder.archive_bundle(plan)
            with zipfile.ZipFile(artifact) as archive:
                names = archive.namelist()
                self.assertIn('Discord TTS GUI/Discord TTS GUI.exe', names)
                self.assertIn('README.md', names)
                for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', archive.read('README.md').decode()):
                    if '://' not in target and not target.startswith('#'):
                        self.assertTrue(target in names or any(name.startswith(target.rstrip('/') + '/')
                                                               for name in names), target)
                self.assertTrue(any(name.startswith('licenses/') for name in names))
                self.assertNotIn('.env', names)
                self.assertFalse(any('.venv' in name or '.git/' in name for name in names))
            self.assertTrue(artifact.with_name(artifact.name + '.sha256').is_file())

    def test_build_sources_remain_python_310_compatible(self):
        for name in ('build_desktop.py', 'build_deb.py', 'desktop_entry.py', 'launcher.py'):
            source = ROOT / 'packaging' / name
            ast.parse(source.read_text(encoding='utf-8'), feature_version=(3, 10))

    def test_native_and_deb_include_same_application_modules(self):
        spec = importlib.util.spec_from_file_location('deb_builder', ROOT / 'packaging/build_deb.py')
        deb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deb)
        self.assertEqual(set(deb.APP_SOURCES), {name + '.py' for name in builder.MODULES})
        self.assertEqual(deb.VERSION, builder.VERSION)

    def test_ci_uses_native_runners_and_only_uploads_artifacts(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        for label in ('ubuntu-22.04', 'windows-latest', 'macos-15', 'macos-15-intel'):
            self.assertIn(label, workflow)
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn('upload-artifact@', workflow)
        self.assertNotIn('gh release', workflow)
        self.assertNotIn('contents: write', workflow)


if __name__ == '__main__':
    unittest.main()
