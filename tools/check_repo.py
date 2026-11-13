#!/usr/bin/env python3
"""Fast offline repository checks; no application imports or generated files."""
import argparse
import ast
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

# Direct execution and importlib-based consumers both work without installing tools.
# Loading source directly avoids creating bytecode even without Python's -B flag.
_manifest_path = Path(__file__).with_name('export_source.py')
_manifest = {'__file__': str(_manifest_path), '__name__': '_source_manifest'}
exec(compile(_manifest_path.read_text(encoding='utf-8'), str(_manifest_path), 'exec'), _manifest)
source_files = _manifest['source_files']
ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCS = (
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'GEMINI.md', 'CONTRIBUTING.md',
    'docs/README.md', 'docs/architecture.md', 'docs/development.md',
    'docs/testing.md', 'docs/releasing.md', 'docs/troubleshooting.md',
    'docs/harness/README.md', 'docs/harness/invariants.md',
    'docs/harness/workflow.md', 'docs/harness/quality.md', 'docs/harness/agents.md',
)


def _literal_assignment(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                break
            if isinstance(value, (tuple, list)) and all(isinstance(item, str) for item in value):
                return tuple(value)
    raise ValueError(f'{name} must be an explicit tuple/list of source names')


def _document_links(text):
    # Ignore examples within fenced/inline code; inspect inline, reference and HTML links.
    text = re.sub(r'^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text, flags=re.M | re.S)
    text = re.sub(r'`[^`\n]*`', '', text)
    links = re.findall(r'!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)', text)
    links += re.findall(r'^\s{0,3}\[[^\]\n]+\]:\s*(<[^>]+>|\S+)', text, flags=re.M)
    links += re.findall(r'(?:href|src)\s*=\s*[\"\']([^\"\']+)', text, flags=re.I)
    return [link.strip('<>') for link in links]


def check_repository(root):
    """Return actionable problems found in a checkout or an extracted source ZIP."""
    root = Path(root).resolve()
    errors = []
    for name in REQUIRED_DOCS:
        if not (root / name).is_file():
            errors.append(f'{name}: missing required guide; restore the entry document')
    for path in sorted(root.glob('test_*.py')):
        errors.append(f'{path.name}: move regression tests into tests/')
    try:
        files = source_files(root)
    except (OSError, ValueError) as error:
        return errors + [str(error)]

    trees = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative.startswith('packaging/vendor/'):
            continue
        if path.suffix == '.py':
            try:
                trees[relative] = ast.parse(path.read_text(encoding='utf-8-sig'),
                                            filename=relative, feature_version=(3, 10))
            except (SyntaxError, UnicodeError) as error:
                line = getattr(error, 'lineno', 1)
                errors.append(f'{relative}:{line}: Python 3.10 syntax error: {error}')
        if path.suffix.lower() == '.md' and not relative.startswith('docs/plans/archive/'):
            text = path.read_text(encoding='utf-8')
            if re.search(r'(?:/home/[^/\s]+/|/Users/[^/\s]+/|[A-Z]:\\Users\\[^\\\s]+\\)', text):
                errors.append(f'{relative}: replace machine-specific user paths with portable examples')
            for link in _document_links(text):
                target = urlsplit(link)
                if target.scheme or target.netloc or not target.path:
                    continue
                destination = (root if target.path.startswith('/') else path.parent) / unquote(target.path).lstrip('/')
                if not destination.exists():
                    errors.append(f'{relative}: broken link {link!r}; fix the target or restore the file')

    production = {path.stem for path in files if path.parent == root and path.suffix == '.py'}
    for builder, constant in (('packaging/build_desktop.py', 'MODULES'),
                              ('packaging/build_deb.py', 'APP_SOURCES')):
        tree = trees.get(builder)
        if tree is None:
            errors.append(f'{builder}: missing or invalid packaging builder')
            continue
        try:
            names = _literal_assignment(tree, constant)
        except ValueError as error:
            errors.append(f'{builder}: {error}')
            continue
        modules = {name.removesuffix('.py') for name in names}
        for module in sorted(production - modules):
            errors.append(f'{builder}: {constant} omits production module {module}.py')
        for module in sorted(modules - production):
            errors.append(f'{builder}: {constant} references missing source {module}.py')
    desktop_tree = trees.get('packaging/build_desktop.py')
    if desktop_tree:
        try:
            workers = _literal_assignment(desktop_tree, 'WORKER_SOURCES')
            for required in ('neural_runtime.py', 'neural_model_files.py'):
                if required not in workers:
                    errors.append(f'packaging/build_desktop.py: WORKER_SOURCES must include {required}')
            for name in workers:
                if name not in trees:
                    errors.append(f'packaging/build_desktop.py: missing worker source {name}')
        except ValueError as error:
            errors.append(f'packaging/build_desktop.py: {error}')

    for name in ('neural_runtime.py', 'portable_audio.py', 'portable_playback.py',
                 'runtime_support.py', 'media_tools.py'):
        tree = trees.get(name)
        if not tree:
            continue
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        forbidden = ((production - {'neural_model_files'}) if name == 'neural_runtime.py'
                     else {'app', 'desktop_ui', 'qt_ui'})
        for module in sorted(imports & forbidden):
            errors.append(f'{name}: import {module} crosses the worker/portable boundary; keep GUI dependencies outside this module')
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        errors = check_repository(ROOT)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Repository check failed: {error}\n')
    if errors:
        print('\n'.join(f'ERROR: {error}' for error in errors), file=sys.stderr)
        print(f'Repository check failed: {len(errors)} problem(s)', file=sys.stderr)
        return 1
    print('Repository checks passed: guides, links, Python 3.10 syntax, packaging sources and import boundaries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
