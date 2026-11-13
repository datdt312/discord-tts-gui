"""Keep ONNX external data beside regular graph files, outside Hub's blobs."""
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import neural_model_files as model_files
except ModuleNotFoundError:
    model_files = None


class ModelFileTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(model_files, 'the model cache materializer must exist')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.hub = self.root / 'huggingface' / 'hub'
        self.snapshot = self.hub / 'models--owner--model' / 'snapshots' / 'commit-one'
        self.cache = self.root / 'onnx-models'

    def cached_file(self, name, data, blob):
        source = self.hub / 'blobs' / blob[:2] / blob
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
        path = self.snapshot / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(os.path.relpath(source, path.parent))
        return path

    def test_sharded_graph_and_nested_external_weights_become_independent_copies(self):
        graph = self.cached_file('onnx/graph.onnx', b'graph', '8b-graph')
        weights = self.cached_file('onnx/weights/shared.data', b'weights', '5c-weights')
        staged_graph = Path(model_files.materialize_model_file(graph, self.cache))
        staged_weights = Path(model_files.materialize_model_file(weights, self.cache))
        self.assertEqual(staged_graph.parent / 'weights' / 'shared.data', staged_weights)
        self.assertEqual(staged_weights.read_bytes(), b'weights')
        for original, staged in ((graph, staged_graph), (weights, staged_weights)):
            self.assertFalse(staged.is_symlink())
            self.assertNotEqual(staged.stat().st_ino, original.stat().st_ino)
            self.assertTrue(original.is_symlink())
            self.assertTrue(staged.is_relative_to(self.cache))
        staged_weights.write_bytes(b'edited!')
        self.assertEqual(weights.read_bytes(), b'weights')

    def test_unchanged_source_reuses_copy_and_retargeted_blob_refreshes_it(self):
        source = self.cached_file('graph.onnx', b'old', '8b-old')
        staged = Path(model_files.materialize_model_file(source, self.cache))
        before = staged.stat()
        with patch('neural_model_files.shutil.copyfile', side_effect=AssertionError('copied again')):
            self.assertEqual(Path(model_files.materialize_model_file(source, self.cache)), staged)
        self.assertEqual(staged.stat().st_mtime_ns, before.st_mtime_ns)
        source.unlink()
        self.cached_file('graph.onnx', b'new', '5c-new')
        self.assertEqual(Path(model_files.materialize_model_file(source, self.cache)), staged)
        self.assertEqual(staged.read_bytes(), b'new')

    def test_source_updates_and_edited_staging_copy_are_repaired(self):
        source = self.cached_file('graph.onnx', b'old', '8b-old')
        staged = Path(model_files.materialize_model_file(source, self.cache))
        source.resolve().write_bytes(b'updated model')
        model_files.materialize_model_file(source, self.cache)
        self.assertEqual(staged.read_bytes(), b'updated model')
        staged.write_bytes(b'changed model')
        model_files.materialize_model_file(source, self.cache)
        self.assertEqual(staged.read_bytes(), b'updated model')

    def test_repositories_and_snapshot_revisions_do_not_share_staged_files(self):
        first = self.cached_file('graph.onnx', b'first', '8b-first')
        self.snapshot = self.hub / 'models--owner--model' / 'snapshots' / 'commit-two'
        second = self.cached_file('graph.onnx', b'second', '5c-second')
        self.snapshot = self.hub / 'models--other--model' / 'snapshots' / 'commit-one'
        third = self.cached_file('graph.onnx', b'third', '6d-third')
        staged = [Path(model_files.materialize_model_file(path, self.cache))
                  for path in (first, second, third)]
        self.assertEqual(len(set(staged)), 3)
        self.assertEqual([path.read_bytes() for path in staged], [b'first', b'second', b'third'])

    def test_failed_copy_keeps_previous_file_and_removes_partial_temporary_file(self):
        source = self.cached_file('graph.onnx', b'old', '8b-old')
        staged = Path(model_files.materialize_model_file(source, self.cache))
        source.resolve().write_bytes(b'new model')
        def interrupted_copy(source, destination):
            Path(destination).write_bytes(b'partial')
            raise OSError('disk full')
        with patch('neural_model_files.shutil.copyfile', side_effect=interrupted_copy):
            with self.assertRaisesRegex(OSError, 'disk full'):
                model_files.materialize_model_file(source, self.cache)
        self.assertEqual(staged.read_bytes(), b'old')
        self.assertEqual(list(staged.parent.iterdir()), [staged])
        model_files.materialize_model_file(source, self.cache)
        self.assertEqual(staged.read_bytes(), b'new model')

    def test_destination_directory_symlink_cannot_write_outside_staging_cache(self):
        source = self.cached_file('onnx/graph.onnx', b'graph', '8b-graph')
        staged = Path(model_files.materialize_model_file(source, self.cache))
        staged.unlink()
        staged.parent.rmdir()
        outside = self.root / 'outside'
        outside.mkdir()
        staged.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            model_files.materialize_model_file(source, self.cache)
        self.assertEqual(list(outside.iterdir()), [])

    def test_wrapper_preserves_download_arguments_progress_and_nonpath_results(self):
        source = self.cached_file('graph.onnx', b'graph', '8b-graph')
        dry_run = object()
        calls = []
        def existing_download(*args, **kwargs):
            calls.append((args, kwargs))
            return dry_run if kwargs.get('dry_run') else str(source)
        hub = types.ModuleType('huggingface_hub')
        hub.hf_hub_download = existing_download
        with patch.dict('sys.modules', {'huggingface_hub': hub}), patch.dict(
                os.environ, {'HF_HOME': str(self.hub.parent)}):
            model_files.install_local_model_files()
            installed = hub.hf_hub_download
            staged = Path(installed('owner/model', 'graph.onnx', local_files_only=True))
            model_files.install_local_model_files()
            self.assertIs(hub.hf_hub_download, installed)
            self.assertIs(installed('owner/model', 'graph.onnx', dry_run=True), dry_run)
        self.assertTrue(staged.is_relative_to(self.cache))
        self.assertFalse(staged.is_symlink())
        self.assertEqual(calls, [(('owner/model', 'graph.onnx'), {'local_files_only': True}),
                                 (('owner/model', 'graph.onnx'), {'dry_run': True})])

    def test_default_cache_without_hf_home_uses_application_xdg_cache(self):
        source = self.root / 'model.json'
        source.write_text('{}')
        with patch.dict(os.environ, {'XDG_CACHE_HOME': str(self.root / 'xdg')}, clear=True):
            staged = Path(model_files.materialize_model_file(source))
        self.assertTrue(staged.is_relative_to(self.root / 'xdg' / 'discord-tts-gui' / 'onnx-models'))
        self.assertEqual(staged.read_text(), '{}')

    def test_missing_optional_hub_dependency_is_a_noop(self):
        with patch.dict('sys.modules', {'huggingface_hub': None}):
            self.assertIsNone(model_files.install_local_model_files())


if __name__ == '__main__':
    unittest.main()
