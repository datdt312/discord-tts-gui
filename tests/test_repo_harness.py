"""Offline integration tests for repository checks and safe source exports."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo'
        self.root.mkdir()
        for name in ('README.md', 'AGENTS.md', 'CLAUDE.md', 'GEMINI.md',
                     'CONTRIBUTING.md', 'docs/README.md', 'docs/architecture.md',
                     'docs/development.md', 'docs/testing.md', 'docs/releasing.md',
                     'docs/troubleshooting.md', 'docs/harness/README.md',
                     'docs/harness/invariants.md', 'docs/harness/workflow.md',
                     'docs/harness/quality.md', 'docs/harness/agents.md'):
            self.write(name, '# Guide\n')
        self.write('README.md', '[Development](docs/development.md#setup)\n')
        self.write('app.py', 'VERSION = "1.3.0"\n')
        self.write('neural_runtime.py', 'from neural_model_files import setup\n')
        self.write('neural_model_files.py', 'def setup():\n    pass\n')
        self.write('portable_audio.py', 'import sys\n')
        self.write('packaging/build_desktop.py',
                   "MODULES = ('app', 'neural_runtime', 'neural_model_files', 'portable_audio')\n"
                   "WORKER_SOURCES = ('neural_runtime.py', 'neural_model_files.py')\n")
        self.write('packaging/build_deb.py',
                   "APP_SOURCES = ('app.py', 'neural_runtime.py', 'neural_model_files.py', 'portable_audio.py')\n")

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def load(self, name):
        path = ROOT / 'tools' / (name + '.py')
        self.assertTrue(path.is_file(), 'Implement the offline ' + name + ' tool')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def check(self):
        return self.load('check_repo').check_repository(self.root)

    def export(self):
        output = self.root / 'dist/source.zip'
        self.load('export_source').export_source(self.root, output)
        return output

    def test_valid_repository_passes_without_creating_files(self):
        before = set(self.root.rglob('*'))
        self.assertEqual(self.check(), [])
        self.assertEqual(set(self.root.rglob('*')), before)

    def test_broken_document_link_identifies_file_and_target(self):
        self.write('docs/testing.md', '[Missing](missing.md)\n')
        errors = '\n'.join(self.check())
        self.assertIn('docs/testing.md', errors)
        self.assertIn('missing.md', errors)

    def test_reference_and_html_links_are_checked_but_archived_plans_are_historical(self):
        self.write('docs/testing.md', '[Guide][guide]\n\n[guide]: absent.md\n<a href="also-absent.md">Guide</a>\n')
        self.write('docs/plans/archive/history.md', '[Old](removed.md)\n')
        errors = '\n'.join(self.check())
        self.assertIn('absent.md', errors)
        self.assertIn('also-absent.md', errors)
        self.assertNotIn('removed.md', errors)

    def test_bad_python_is_reported_with_path_and_line(self):
        self.write('app.py', 'def broken(\n')
        errors = '\n'.join(self.check())
        self.assertIn('app.py:1', errors)
        self.assertIn('syntax', errors.lower())

    def test_missing_worker_and_packaging_manifest_drift_are_reported(self):
        (self.root / 'neural_model_files.py').unlink()
        errors = '\n'.join(self.check())
        self.assertIn('neural_model_files.py', errors)
        self.assertIn('packaging/build_desktop.py', errors)

    def test_private_worker_cannot_import_gui_and_tests_belong_under_tests(self):
        self.write('neural_runtime.py', 'import app\n')
        self.write('test_accidental.py', 'pass\n')
        errors = '\n'.join(self.check())
        self.assertIn('neural_runtime.py', errors)
        self.assertIn('import', errors)
        self.assertIn('test_accidental.py', errors)

    def test_exports_workers_licenses_agent_guides_and_ci(self):
        included = ('packaging/licenses/LICENSE.txt', 'packaging/vendor/certifi/cacert.pem',
                    '.github/workflows/check.yml', 'tests/test_example.py',
                    'tools/check_repo.py', 'docs/AGENTS.md', '.editorconfig', '.gitattributes')
        for name in included:
            self.write(name, 'public source\n')
        with zipfile.ZipFile(self.export()) as archive:
            names = set(archive.namelist())
            self.assertTrue(set(included) <= names)
            self.assertTrue({'neural_runtime.py', 'neural_model_files.py', 'AGENTS.md',
                             'CLAUDE.md', 'GEMINI.md'} <= names)

    def test_excludes_nested_secrets_caches_models_builds_and_ignored_files(self):
        excluded = ('docs/.env', 'docs/sub/.env.private', 'docs/sub/private-key.pem',
                    'docs/id_rsa', 'docs/cache.log', 'packaging/vendor/__pycache__/a.pyc',
                    'packaging/vendor/.venv/lib/site.py', 'docs/models/weights.onnx',
                    'docs/data/weights.safetensors', 'tests/dist/old.py', 'tools/build/old.py',
                    'docs/.cache/data', '.agents/session.json', '.codex/session.json',
                    'docs/private.txt', 'docs/nested/private.txt', 'notes.txt')
        self.write('.gitignore', 'private.txt\n')
        for name in excluded:
            self.write(name, 'private data\n')
        self.write('docs/.env.example', 'OPTION=value\n')
        with zipfile.ZipFile(self.export()) as archive:
            names = set(archive.namelist())
            self.assertFalse(set(excluded) & names)
            self.assertIn('docs/.env.example', names)

    def test_nested_gitignore_negation_keeps_explicit_public_example(self):
        self.write('docs/.gitignore', '*.txt\n!public.txt\n')
        self.write('docs/private.txt', 'private\n')
        self.write('docs/public.txt', 'public\n')
        with zipfile.ZipFile(self.export()) as archive:
            self.assertNotIn('docs/private.txt', archive.namelist())
            self.assertIn('docs/public.txt', archive.namelist())

    def test_nested_recordings_agent_state_and_binary_artifacts_are_excluded(self):
        excluded = ('docs/recordings/private.wav', 'docs/data/speech.mp3',
                    'docs/data/speech.pcm', 'docs/.claude/projects/session.json',
                    'docs/model-cache/weights.data', 'packaging/data/model.gguf',
                    'packaging/data/runtime.bundle')
        for name in excluded:
            self.write(name, 'private or generated data\n')
        with zipfile.ZipFile(self.export()) as archive:
            self.assertEqual(set(excluded) & set(archive.namelist()), set())

    def test_output_alias_cannot_overwrite_owned_source(self):
        self.write('tools/helper.py', 'pass\n')
        original = (self.root / 'app.py').read_bytes()
        with self.assertRaisesRegex(ValueError, 'source manifest'):
            self.load('export_source').export_source(
                self.root, self.root / 'tools' / '..' / 'app.py')
        self.assertEqual((self.root / 'app.py').read_bytes(), original)

    def test_output_symlink_is_rejected_without_modifying_target(self):
        target = Path(self.temporary.name) / 'private.txt'
        target.write_text('private data', encoding='utf-8')
        output = self.root / 'source.zip'
        output.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.load('export_source').export_source(self.root, output)
        self.assertEqual(target.read_text(encoding='utf-8'), 'private data')

    def test_symlink_escape_is_rejected_before_output_is_written(self):
        outside = Path(self.temporary.name) / 'private.txt'
        outside.write_text('private', encoding='utf-8')
        (self.root / 'docs/escape.md').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.export()
        self.assertFalse((self.root / 'dist/source.zip').exists())

    def test_export_is_reproducible_and_extracts_without_source_checkout(self):
        output = self.export()
        first = output.read_bytes()
        self.export()
        self.assertEqual(first, output.read_bytes())
        extracted = Path(self.temporary.name) / 'extracted'
        with zipfile.ZipFile(output) as archive:
            archive.extractall(extracted)
        ast.parse((extracted / 'app.py').read_text(encoding='utf-8'), feature_version=(3, 10))
        self.assertTrue((extracted / 'neural_runtime.py').is_file())

    def test_real_export_supports_desktop_build_plan_after_extraction(self):
        output = Path(self.temporary.name) / 'real.zip'
        self.load('export_source').export_source(ROOT, output)
        extracted = Path(self.temporary.name) / 'standalone'
        with zipfile.ZipFile(output) as archive:
            archive.extractall(extracted)
        result = subprocess.run([sys.executable, '-B', 'packaging/build_desktop.py',
                                 '--plan', '--target', 'windows'], cwd=extracted,
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('workers/neural_runtime.py', json.loads(result.stdout)['worker_sources'])
        ast.parse((extracted / 'app.py').read_text(encoding='utf-8'), feature_version=(3, 10))


if __name__ == '__main__':
    unittest.main()
