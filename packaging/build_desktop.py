#!/usr/bin/env python3
"""Build a desktop bundle on its target OS; --plan needs no build dependencies.

Install requirements-build.txt, then run this script on Windows, macOS or Linux.
The native .deb remains available separately through build_deb.py. This builder
never downloads models, private Python environments, or audio routing drivers.
"""
import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION = '1.3.0'
APP_NAME = 'Discord TTS GUI'
MODULES = ('app', 'desktop_ui', 'qt_ui', 'neural_backend', 'neural_playback',
           'neural_runtime', 'neural_model_files', 'runtime_support',
           'media_tools', 'portable_audio', 'portable_playback')
WORKER_SOURCES = ('neural_runtime.py', 'neural_model_files.py')
COLLECT_PACKAGES = ('PyQt6', 'edge_tts', 'certifi', 'imageio_ffmpeg', 'sounddevice')
EXCLUDED_MODULES = ('PyQt5', 'PySide2', 'PySide6', 'pytest', 'unittest',
                    'torch', 'transformers', 'vieneu', 'huggingface_hub')


def host_target():
    return {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux'
               if sys.platform.startswith('linux') else sys.platform)


def architecture(machine=None):
    value = (machine or platform.machine()).lower()
    return {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(value, value)


def build_plan(target=None, output_dir=None, machine=None):
    target = target or host_target()
    if target not in ('windows', 'macos', 'linux'):
        raise ValueError('Supported targets: windows, macos, linux')
    arch = architecture(machine)
    output = Path(output_dir or ROOT / 'dist').resolve()
    work = output / 'desktop-build'
    separator = ';' if target == 'windows' else ':'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--onedir', '--name', APP_NAME, '--paths', str(ROOT),
               '--distpath', str(work / 'dist'), '--workpath', str(work / 'work'),
               '--specpath', str(work / 'spec')]
    if target in ('windows', 'macos'):
        command.append('--windowed')
    if target == 'macos':
        command.extend(['--osx-bundle-identifier', 'local.discordttsgui.desktop',
                        '--target-architecture', arch])
    for module in MODULES:
        command.extend(['--hidden-import', module])
    for package in COLLECT_PACKAGES:
        command.extend(['--collect-all', package])
    if target != 'linux':
        command.extend(['--collect-all', '_sounddevice_data'])
    # sounddevice imports a generated CFFI module dynamically.
    command.extend(['--hidden-import', '_sounddevice', '--hidden-import', '_cffi_backend'])
    for module in EXCLUDED_MODULES:
        command.extend(['--exclude-module', module])
    for name in WORKER_SOURCES:
        command.extend(['--add-data', str(ROOT / name) + separator + 'workers'])
    command.extend(['--add-binary', '<uv executable>' + separator + 'tools'])
    command.append(str(ROOT / 'packaging/desktop_entry.py'))
    suffix = '.tar.gz' if target == 'linux' else '.zip'
    return {'version': VERSION, 'target': target, 'architecture': arch,
            'native_build_required': True,
            'artifact': str(output / f'discord-tts-gui-{VERSION}-{target}-{arch}{suffix}'),
            'bundle': str(work / 'dist' / (APP_NAME + ('.app' if target == 'macos' else ''))),
            'command': command, 'modules': list(MODULES),
            'worker_sources': ['workers/' + name for name in WORKER_SOURCES],
            'resources': ['tools/uv.exe' if target == 'windows' else 'tools/uv',
                          'imageio_ffmpeg/binaries', '_sounddevice_data'],
            'excluded': list(EXCLUDED_MODULES)}


def find_uv_binary():
    try:
        import uv
        candidate = Path(uv.find_uv_bin())
        if candidate.is_file():
            return candidate.resolve()
    except (ImportError, AttributeError, FileNotFoundError):
        pass
    candidate = shutil.which('uv')
    if candidate:
        return Path(candidate).resolve()
    raise RuntimeError('uv is required for private Python setup. Install requirements-build.txt.')


def validate_build_environment():
    missing = [name for name in ('PyInstaller', 'PyQt6', 'edge_tts',
                                'imageio_ffmpeg', 'sounddevice')
               if importlib.util.find_spec(name) is None]
    if host_target() != 'linux' and importlib.util.find_spec('_sounddevice_data') is None:
        missing.append('_sounddevice_data')
    if missing:
        raise RuntimeError('Missing build dependencies: ' + ', '.join(missing) +
                           '. Install requirements-build.txt.')
    for name in MODULES:
        if not (ROOT / (name + '.py')).is_file():
            raise RuntimeError('Missing application source: ' + name + '.py')


def archive_bundle(plan):
    artifact = Path(plan['artifact'])
    bundle = Path(plan['bundle'])
    if not bundle.is_dir():
        raise RuntimeError('PyInstaller did not produce the expected bundle: ' + str(bundle))
    # Stage only explicit deliverables. Never archive the repository or build venv.
    with tempfile.TemporaryDirectory(prefix='tts-desktop-package-') as directory:
        stage = Path(directory)
        shutil.copytree(bundle, stage / bundle.name, symlinks=True)
        for name in ('README.md', 'requirements-desktop.txt'):
            shutil.copy2(ROOT / name, stage / name)
        shutil.copytree(ROOT / 'packaging/licenses', stage / 'licenses')
        shutil.copy2(ROOT / 'packaging/copyright', stage / 'copyright')
        if plan['target'] == 'macos':
            # ditto preserves executable permissions, framework links and .app metadata.
            subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', str(stage),
                            str(artifact)], check=True)
        else:
            archive_format = 'gztar' if plan['target'] == 'linux' else 'zip'
            extension = '.tar.gz' if archive_format == 'gztar' else '.zip'
            shutil.make_archive(str(artifact)[:-len(extension)], archive_format,
                                root_dir=stage)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_name(artifact.name + '.sha256').write_text(
        digest + '  ' + artifact.name + '\n', encoding='utf-8')
    return artifact


def build(target=None, output_dir=None):
    plan = build_plan(target, output_dir)
    if plan['target'] != host_target():
        raise RuntimeError('Native build required: run this builder on ' + plan['target'] +
                           '. Use --plan to inspect commands on another OS.')
    validate_build_environment()
    uv = find_uv_binary()
    command = [part.replace('<uv executable>', str(uv)) for part in plan['command']]
    Path(plan['artifact']).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True, cwd=ROOT)
    artifact = archive_bundle(plan)
    print('Created: ' + str(artifact))
    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('windows', 'macos', 'linux'))
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--plan', '--dry-run', action='store_true',
                        help='Print a JSON build plan without imports, downloads or builds')
    args = parser.parse_args(argv)
    try:
        if args.plan:
            print(json.dumps(build_plan(args.target, args.output_dir), indent=2))
        else:
            build(args.target, args.output_dir)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
