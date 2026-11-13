#!/usr/bin/env python3
"""Build an architecture-independent .deb using only Python and dpkg-deb."""
import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION = '1.2.0'
DEPENDENCIES = ('python3 (>= 3.10), python3-tk, python3-pyqt6 | python3-pyqt5, '
                'python3-venv, libsndfile1, '
                'python3-aiohttp (>= 3.8.0), '
                'python3-aiohttp (<< 4.0), '
                'ffmpeg, pulseaudio-utils, espeak-ng, xauth')


def build(output_dir):
    if shutil.which('dpkg-deb') is None:
        raise RuntimeError('dpkg-deb is required (install dpkg-dev on Ubuntu/Debian).')
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    packaging = ROOT / 'packaging'
    with tempfile.TemporaryDirectory(prefix='discord-tts-deb-') as temporary:
        stage = Path(temporary) / 'package'
        appdir = stage / 'usr/share/discord-tts-gui'
        docs = stage / 'usr/share/doc/discord-tts-gui'
        appdir.mkdir(parents=True)
        docs.mkdir(parents=True)
        for name in ('app.py', 'neural_backend.py', 'neural_runtime.py', 'neural_playback.py',
                     'neural_model_files.py', 'desktop_ui.py', 'qt_ui.py'):
            shutil.copy2(ROOT / name, appdir / name)
        shutil.copy2(packaging / 'launcher.py', appdir / 'launcher.py')
        shutil.copytree(packaging / 'vendor', appdir / 'vendor',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(packaging / 'licenses', docs / 'licenses')
        for name in ('README.vi.txt', 'copyright', 'VENDORED.txt'):
            shutil.copy2(packaging / name, docs / name)
        shutil.copy2(ROOT / 'README.md', docs / 'README.md')
        for relative, source in (
            ('usr/bin/discord-tts-gui', 'discord-tts-gui'),
            ('usr/share/applications/discord-tts-gui-packaged.desktop',
             'discord-tts-gui-packaged.desktop'),
            ('usr/share/icons/hicolor/scalable/apps/discord-tts-gui.svg', 'discord-tts-gui.svg'),
        ):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(packaging / source, target)

        control = stage / 'DEBIAN'
        control.mkdir()
        size = sum(path.stat().st_size for path in (stage / 'usr').rglob('*') if path.is_file())
        (control / 'control').write_text(
            'Package: discord-tts-gui\n'
            f'Version: {VERSION}\n'
            'Section: sound\n'
            'Priority: optional\n'
            'Architecture: all\n'
            'Maintainer: Discord TTS GUI <noreply@localhost>\n'
            f'Installed-Size: {(size + 1023) // 1024}\n'
            f'Depends: {DEPENDENCIES}\n'
            'Description: Streaming text-to-speech virtual microphone for Discord\n'
            ' Read Vietnamese and English text through a temporary virtual microphone.\n'
            ' Microsoft Edge voices stream online; eSpeak NG is available offline.\n',
            encoding='utf-8')
        hashes = []
        for path in sorted((stage / 'usr').rglob('*')):
            if path.is_file():
                digest = hashlib.md5(path.read_bytes()).hexdigest()
                hashes.append(f'{digest}  {path.relative_to(stage).as_posix()}\n')
        (control / 'md5sums').write_text(''.join(hashes), encoding='utf-8')
        epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '1794528000'))
        for path in [stage, *stage.rglob('*')]:
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.utime(path, (epoch, epoch))
        (stage / 'usr/bin/discord-tts-gui').chmod(0o755)
        package = output_dir / f'discord-tts-gui_{VERSION}_all.deb'
        environment = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch))
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build',
                        str(stage), str(package)], check=True, env=environment)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (output_dir / 'SHA256SUMS').write_text(f'{digest}  {package.name}\n', encoding='utf-8')
    print(f'Created: {package}\nSHA256: {digest}')
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    arguments = parser.parse_args()
    build(arguments.output_dir)
