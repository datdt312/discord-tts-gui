"""Resolve optional native tools without assuming a Unix installation."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def current_platform():
    return sys.platform


def ffmpeg_executable():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError) as error:
        raise RuntimeError('FFmpeg is unavailable. Install the desktop dependencies with '
                           'python -m pip install -r requirements-desktop.txt, '
                           'or install FFmpeg on PATH.') from error


def espeak_executable():
    executable = shutil.which('espeak-ng')
    if executable:
        return executable
    if current_platform() == 'win32':
        for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
            directory = os.environ.get(variable)
            if directory:
                candidate = Path(directory) / 'eSpeak NG' / 'espeak-ng.exe'
                if candidate.is_file():
                    return str(candidate)
    raise RuntimeError('eSpeak NG is optional and is not installed. Install eSpeak NG '
                       'or select VieNeu-TTS / Microsoft Edge instead.')


def subprocess_options():
    """Avoid extra console windows when a packaged Windows GUI starts tools."""
    return {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)} \
        if current_platform() == 'win32' else {}
