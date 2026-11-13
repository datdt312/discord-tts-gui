#!/usr/bin/env python3
"""Export an explicit, reproducible source bundle without Git or dependencies.

Only root Python modules, project entry files, requirements, and owned source
folders are eligible. Personal state, builds, models and ignored files are
excluded at every depth. Symlinks in eligible source are rejected. Public
vendored certificate bundles (cacert.pem) remain part of the source.
"""
import argparse
import fnmatch
from pathlib import Path
import re
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.3.0'
ROOT_FILES = frozenset({
    'README.md', '.gitignore', '.gitattributes', '.editorconfig',
    'AGENTS.md', 'CLAUDE.md', 'GEMINI.md', 'CONTRIBUTING.md',
    'LICENSE', 'LICENSE.md', 'LICENSE.txt', 'NOTICE', 'NOTICE.md',
    'install.sh', 'start-windows.bat', 'start-macos.command',
})
SOURCE_DIRECTORIES = ('tests', 'docs', 'tools', '.github', 'packaging')
EXCLUDED_DIRECTORIES = frozenset({
    '.git', '.agents', '.codex', '.claude', '.aws', '.ssh', '__pycache__',
    '.pytest_cache', '.mypy_cache', '.ruff_cache', '.cache',
    'dist', 'build', 'venv', 'env', 'node_modules', 'models',
    'model_cache', 'model-cache', 'recordings', 'logs', 'htmlcov',
})
EXCLUDED_SUFFIXES = frozenset({
    '.pyc', '.pyo', '.log', '.onnx', '.safetensors', '.pt', '.pth',
    '.ckpt', '.bin', '.zip', '.tar', '.gz', '.deb', '.exe', '.dll',
    '.so', '.dylib', '.key', '.p12', '.pfx', '.gguf', '.bundle',
    '.wav', '.mp3', '.pcm',
})


def _excluded(path):
    """Deny generated/personal data even if an ignore rule tries to include it."""
    if any(part in EXCLUDED_DIRECTORIES or part.startswith('.venv')
           or part.endswith('.egg-info') for part in path.parts):
        return True
    name = path.name.lower()
    return ((name == '.env' or name.startswith('.env.')) and name != '.env.example'
            or name.startswith(('id_rsa', 'id_ed25519', 'credentials', 'secrets'))
            or name in {'config.local.json', 'settings.local.json', '.coverage', '.ds_store'}
            or path.suffix.lower() in EXCLUDED_SUFFIXES
            or path.suffix.lower() == '.pem' and name != 'cacert.pem')


def _glob(pattern):
    """Translate ignore globs while keeping '*' within a single path segment."""
    pieces = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if pattern[index:index + 3] == '**/':
            pieces.append('(?:.*/)?')
            index += 3
        elif pattern[index:index + 2] == '**':
            pieces.append('.*')
            index += 2
        elif character == '*':
            pieces.append('[^/]*')
            index += 1
        elif character == '?':
            pieces.append('[^/]')
            index += 1
        elif character == '[':
            end = pattern.find(']', index + 1)
            if end < 0:
                pieces.append(r'\[')
                index += 1
            else:
                group = pattern[index:end + 1]
                # fnmatch owns the bracket-class escaping; only remove its
                # outer full-string wrapper (Python 3.14 uses \z, earlier \Z).
                translated = fnmatch.translate(group)
                pieces.append(translated[4:-3])
                index = end + 1
        else:
            pieces.append(re.escape(character))
            index += 1
    return re.compile('^' + ''.join(pieces) + '$')


def _rules(directory):
    ignore = directory / '.gitignore'
    if not ignore.is_file() or ignore.is_symlink():
        return []
    rules = []
    for line in ignore.read_text(encoding='utf-8').splitlines():
        line = line.rstrip()
        if not line or line.startswith('#'):
            continue
        include = line.startswith('!')
        if include:
            line = line[1:]
        directory_only = line.endswith('/')
        line = line.rstrip('/')
        anchored = line.startswith('/') or '/' in line
        line = line.lstrip('/')
        rules.append((directory, _glob(line), anchored, directory_only, include))
    return rules


def _ignored(path, directory, rules):
    ignored = False
    for base, pattern, anchored, directory_only, include in rules:
        try:
            relative = path.relative_to(base)
        except ValueError:
            continue
        if directory_only and not directory:
            continue
        value = relative.as_posix() if anchored else relative.name
        if pattern.fullmatch(value):
            ignored = not include
    return ignored


def source_files(root):
    """Return sorted owned source paths; do not traverse the rest of the tree.

    Root and nested .gitignore files support comments, negation, anchored paths,
    directory rules, and *, **, ?, [] globs. Ignored directories are pruned,
    matching Git's rule that a child cannot re-include an excluded parent.
    """
    root = Path(root).resolve()
    selected = []
    root_rules = _rules(root)

    def visit(path, rules):
        relative = path.relative_to(root)
        if _excluded(relative):
            return
        if path.is_symlink():
            raise ValueError(f'Refusing source symlink: {relative}; replace it with an owned regular file')
        directory = path.is_dir()
        if _ignored(path, directory, rules):
            return
        if directory:
            child_rules = rules + _rules(path)
            for child in sorted(path.iterdir()):
                visit(child, child_rules)
        elif path.is_file():
            selected.append(path)

    for path in sorted(root.iterdir()):
        if (path.name in ROOT_FILES
                or path.suffix == '.py' and not path.name.startswith('test_')
                or fnmatch.fnmatchcase(path.name, 'requirements*.txt')
                or path.name in SOURCE_DIRECTORIES):
            visit(path, root_rules)
    return sorted(selected, key=lambda path: path.relative_to(root).as_posix())


def export_source(root, output):
    """Write source files with stable names, timestamps, modes, and ordering."""
    root = Path(root).resolve()
    output = Path(output)
    files = source_files(root)  # Validate all source before creating the output.
    if output.is_symlink():
        raise ValueError('Refusing output symlink: ' + str(output))
    output = output.resolve()
    if output in files:
        raise ValueError('Output must be outside the source manifest (use dist/)')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'dist' / f'discord-tts-gui-{VERSION}-source.zip')
    args = parser.parse_args(argv)
    try:
        count = export_source(ROOT, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Source export failed: {error}\n')
    print(f'Exported {count} source files to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
