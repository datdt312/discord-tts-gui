"""Materialize Hub snapshots for ONNX Runtime's external-data path checks.

Hub's snapshot symlinks may point into different sharded blob directories.
ONNX Runtime resolves those symlinks before checking that external weights
stay inside the graph directory. Private, regular copies preserve that check
and leave the shared Hub cache intact.
"""
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def _default_cache_root():
    hf_home = os.environ.get('HF_HOME')
    if hf_home:
        return Path(hf_home).expanduser().parent / 'onnx-models'
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
    return cache / 'discord-tts-gui' / 'onnx-models'


def _snapshot_location(path):
    """Use the logical snapshot path, before resolving its blob symlink."""
    for parent in path.parents:
        if (parent.parent.name == 'snapshots'
                and parent.parent.parent.name.startswith(('models--', 'datasets--', 'spaces--'))):
            return parent, path.relative_to(parent)
    # hf_hub_download(local_dir=...) and small SDK fixtures can return plain
    # files. Preserve sibling relationships for those files as well.
    return path.parent, Path(path.name)


def _file_stamp(path):
    info = path.stat()
    return {'size': info.st_size, 'mtime_ns': info.st_mtime_ns}


def _prepare_parent(path, root):
    # Never follow a staged subdirectory symlink outside our owned cache.
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError('Materialized model path escapes the application cache')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError('Materialized model path escapes the application cache')


def _atomic_write(path, writer):
    """Replace a complete file; interruptions leave the previous copy usable."""
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        writer(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def materialize_model_file(path, cache_root=None):
    """Copy one cached file, preserving its repository/snapshot-relative path.

    Every file fetched for a snapshot shares a staging root, including nested
    external data files. Provenance avoids copying large immutable blobs again
    on each offline launch while detecting changed sources or edited copies.
    """
    source = Path(os.path.abspath(os.fspath(path)))
    snapshot, relative = _snapshot_location(source)
    key = hashlib.sha256(os.fsencode(snapshot)).hexdigest()
    root = Path(cache_root if cache_root is not None else _default_cache_root()).resolve()
    destination = root / key / relative
    metadata_key = hashlib.sha256(os.fsencode(relative)).hexdigest() + '.json'
    metadata_path = root / '.provenance' / key / metadata_key
    _prepare_parent(destination, root)
    _prepare_parent(metadata_path, root)

    resolved_source = source.resolve(strict=True)
    provenance = {'path': str(resolved_source), **_file_stamp(resolved_source)}
    try:
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if (isinstance(metadata, dict) and metadata.get('source') == provenance
                and not destination.is_symlink() and destination.is_file()
                and metadata.get('copy') == _file_stamp(destination)):
            return str(destination)
    except (OSError, ValueError):
        pass

    def copy(temporary):
        shutil.copyfile(resolved_source, temporary)
        if _file_stamp(resolved_source) != {key: provenance[key] for key in ('size', 'mtime_ns')}:
            raise OSError('Cached model source changed while copying')

    _atomic_write(destination, copy)
    metadata = {'source': provenance, 'copy': _file_stamp(destination)}
    _atomic_write(metadata_path, lambda temporary: temporary.write_text(
        json.dumps(metadata), encoding='utf-8'))
    return str(destination)


def install_local_model_files():
    """Wrap the public Hub downloader, after any existing progress wrapper."""
    try:
        import huggingface_hub
    except ModuleNotFoundError as error:
        if error.name == 'huggingface_hub':
            return
        raise
    download = huggingface_hub.hf_hub_download
    if getattr(download, '_discord_tts_local_model_files', False):
        return

    @wraps(download)
    def with_local_files(*args, **kwargs):
        path = download(*args, **kwargs)
        # Hub's dry-run API returns metadata, rather than a filename.
        if not isinstance(path, (str, os.PathLike)):
            return path
        return materialize_model_file(path)

    with_local_files._discord_tts_local_model_files = True
    huggingface_hub.hf_hub_download = with_local_files
