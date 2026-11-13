"""Standard-library paths shared by the UI and optional neural runtime."""
import os
from pathlib import Path
import platform


def _system(system):
    return (system or platform.system()).lower()


def _xdg_home(variable, fallback):
    value = os.environ.get(variable, '')
    path = Path(value).expanduser()
    return path if value and path.is_absolute() else Path.home() / fallback


def user_data_dir(app='discord-tts-gui', *, system=None):
    """Return the private data directory without creating it."""
    system = _system(system)
    if system in ('windows', 'win32'):
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    elif system in ('darwin', 'macos'):
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = _xdg_home('XDG_DATA_HOME', '.local/share')
    return base / app


def user_state_dir(app='discord-tts-gui', *, system=None):
    """Return the log/state directory without creating it."""
    system = _system(system)
    if system in ('windows', 'win32'):
        return user_data_dir(app, system=system)
    if system in ('darwin', 'macos'):
        return Path.home() / 'Library' / 'Logs' / app
    return _xdg_home('XDG_STATE_HOME', '.local/state') / app


def venv_python(environment, *, system=None):
    """Locate a venv interpreter on the requested host platform."""
    environment = Path(environment)
    if _system(system) in ('windows', 'win32'):
        return environment / 'Scripts' / 'python.exe'
    return environment / 'bin' / 'python'
