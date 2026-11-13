"""Exercise the real runtime protocol against a small SDK boundary fixture."""
import base64
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest


SDK = '''
import os, socket, sys, time
class Vieneu:
    def __init__(self, **kwargs):
        assert kwargs == dict(mode="v3turbo", backend="onnx", device="cpu", precision="fp32")
        print("SDK Python log", flush=True)
        os.write(1, b"SDK native log\\n")
        self.sample_rate = 48000
        root = os.environ["HF_HOME"]
        assert os.environ["HF_HUB_CACHE"].startswith(root)
        if "HF_ASSETS_CACHE" in os.environ:
            assert os.environ["HF_ASSETS_CACHE"].startswith(root)
        if "HF_XET_CACHE" in os.environ:
            assert os.environ["HF_XET_CACHE"].startswith(root)
        self.marker = os.path.join(root, "downloaded")
        if os.environ.get("HF_HUB_OFFLINE") == "1":
            assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
            if not os.path.isfile(self.marker):
                raise RuntimeError("model cache missing")
            try:
                socket.create_connection(("127.0.0.1", 9), timeout=.1)
            except PermissionError:
                pass
            else:
                raise AssertionError("network guard missing")
        else:
            os.makedirs(root, exist_ok=True)
            if os.environ.get("NEURAL_FIXTURE_DOWNLOAD"):
                from huggingface_hub import hf_hub_download
                hf_hub_download("fixture/model", os.environ["NEURAL_FIXTURE_DOWNLOAD"])
            open(self.marker, "w").close()
    def list_preset_voices(self):
        return [("Giọng Việt — nữ", "giọng-thật"), ("Giọng nam", "nam")]
    def infer_stream(self, text, voice, apply_watermark):
        assert voice in ("giọng-thật", "nam")
        assert apply_watermark is False
        if text == "hang":
            time.sleep(60)
        if text == "fail":
            raise RuntimeError("fixture synthesis failed")
        if text == "flood":
            for _ in range(10000):
                yield [.125]
            open(os.path.join(os.environ["HF_HOME"], "flood-complete"), "w").close()
            return
        if text == "Xin chào! ă â đ ê ô ơ ư.":
            yield [-2., -.5, 0., .5, 2.]
        else:
            yield [.125, -.125]
'''


TQDM = '''
class tqdm:
    def __init__(self, *args, total=None, initial=0, disable=False, **kwargs):
        self.total, self.n, self.disable = total, initial, disable
        self.display()
    def display(self, *args, **kwargs):
        pass
    def update(self, n=1):
        if not self.disable:
            self.n += n
            self.display()
    def close(self):
        self.display()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
'''


HF = '''
import os, time
from pathlib import Path
from tqdm.auto import tqdm
def hf_hub_download(repo_id, filename, *, tqdm_class=None, **kwargs):
    path = Path(os.environ["HF_HOME"]) / filename
    if filename == "cached.bin":
        path.write_bytes(b"1234567")
        return str(path)
    size = None if filename == "unknown.bin" else (1000 if filename == "throttled.bin" else 10)
    with (tqdm_class or tqdm)(total=size, initial=4 if size == 10 else 0,
                              disable=True, desc=filename) as progress:
        if filename == "unknown.bin":
            progress.update(3)
            path.write_bytes(b"123")
        elif filename == "throttled.bin":
            for _ in range(1000):
                progress.update(1)
            path.write_bytes(b"x" * 1000)
        else:
            progress.update(2)
            if filename == "failed.bin":
                raise RuntimeError("download interrupted")
            if filename == "hanging.bin":
                time.sleep(60)
            progress.update(4)
            path.write_bytes(b"0123456789")
    return str(path)
'''


def runtime_fixture(directory):
    """Copy production runtime beside only the fake external SDK dependency."""
    path = Path(directory)
    runtime = Path(__file__).with_name('neural_runtime.py')
    if not runtime.is_file():
        return None
    shutil.copyfile(runtime, path / 'neural_runtime.py')
    shutil.copyfile(runtime.with_name('neural_model_files.py'), path / 'neural_model_files.py')
    (path / 'vieneu.py').write_text(SDK, encoding='utf-8')
    (path / 'huggingface_hub.py').write_text(HF, encoding='utf-8')
    (path / 'tqdm').mkdir()
    (path / 'tqdm' / '__init__.py').write_text('', encoding='utf-8')
    (path / 'tqdm' / 'auto.py').write_text(TQDM, encoding='utf-8')
    return path / 'neural_runtime.py'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = runtime_fixture(self.directory.name)
        self.assertIsNotNone(self.path, 'neural runtime must exist')
        self.cache = Path(self.directory.name) / 'cache'
        self.env = dict(os.environ, HF_HOME=str(self.cache),
                        HF_HUB_CACHE=str(self.cache / 'hub'))

    def run_runtime(self, mode, requests=()):
        data = ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in requests)
        result = subprocess.run([sys.executable, str(self.path), mode], input=data,
                                text=True, capture_output=True, env=self.env, timeout=5)
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        return result, messages

    def test_download_then_offline_stream_preserves_unicode_and_clips_pcm(self):
        result, messages = self.run_runtime('--download')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(messages[0]['voices'], {'Giọng Việt — nữ': 'giọng-thật', 'Giọng nam': 'nam'})
        result, messages = self.run_runtime('--offline', [
            {'command': 'speak', 'text': 'Xin chào! ă â đ ê ô ơ ư.', 'voice': 'giọng-thật'},
            {'command': 'speak', 'text': 'Again', 'voice': 'nam'},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SDK native log', result.stderr)
        self.assertEqual([m['event'] for m in messages], ['ready', 'audio', 'done', 'audio', 'done'])
        self.assertEqual(base64.b64decode(messages[1]['data']), struct.pack('<hhhhh', -32768, -16384, 0, 16384, 32767))

    def test_missing_cache_fails_offline_without_downloading(self):
        result, messages = self.run_runtime('--offline')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(messages[0]['event'], 'error')
        self.assertIn('model cache missing', messages[0]['message'])
        self.assertFalse((self.cache / 'downloaded').exists())

    def test_failed_utterance_reports_error_without_hiding_it(self):
        self.run_runtime('--download')
        result, messages = self.run_runtime('--offline', [
            {'command': 'speak', 'text': 'fail', 'voice': 'nam'}])
        self.assertEqual(messages[-1]['event'], 'error')
        self.assertIn('fixture synthesis failed', messages[-1]['message'])

    def test_download_reports_resumed_file_bytes_despite_disabled_parent_bars(self):
        self.env.update(NEURAL_FIXTURE_DOWNLOAD='resumed.bin', HF_HUB_DISABLE_PROGRESS_BARS='1')
        result, messages = self.run_runtime('--download')
        self.assertEqual(result.returncode, 0, result.stderr)
        progress = [m for m in messages if m['event'] == 'progress']
        self.assertTrue(progress, 'real byte progress must precede readiness')
        self.assertEqual(progress[0]['filename'], 'resumed.bin')
        self.assertEqual((progress[0]['downloaded'], progress[0]['total']), (4, 10))
        self.assertEqual((progress[-1]['downloaded'], progress[-1]['total']), (10, 10))
        self.assertEqual(messages[-1]['event'], 'ready')
        self.env['NEURAL_FIXTURE_DOWNLOAD'] = 'failed.bin'
        result, messages = self.run_runtime('--offline')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([m['event'] for m in messages], ['ready'])

    def test_cached_file_reports_actual_completed_file_size(self):
        self.env['NEURAL_FIXTURE_DOWNLOAD'] = 'cached.bin'
        result, messages = self.run_runtime('--download')
        self.assertEqual(result.returncode, 0, result.stderr)
        progress = [m for m in messages if m['event'] == 'progress']
        self.assertEqual(progress, [{'event': 'progress', 'filename': 'cached.bin',
                                    'downloaded': 7, 'total': 7, 'cached': True}])

    def test_unknown_file_size_remains_unknown_until_successful_stat(self):
        self.env['NEURAL_FIXTURE_DOWNLOAD'] = 'unknown.bin'
        result, messages = self.run_runtime('--download')
        self.assertEqual(result.returncode, 0, result.stderr)
        progress = [m for m in messages if m['event'] == 'progress']
        self.assertTrue(any(m['total'] is None for m in progress))
        self.assertEqual((progress[-1]['downloaded'], progress[-1]['total']), (3, 3))

    def test_failed_download_never_claims_file_is_complete(self):
        self.env['NEURAL_FIXTURE_DOWNLOAD'] = 'failed.bin'
        result, messages = self.run_runtime('--download')
        self.assertNotEqual(result.returncode, 0)
        progress = [m for m in messages if m['event'] == 'progress']
        self.assertTrue(progress)
        self.assertEqual(progress[-1]['downloaded'], 6)
        self.assertTrue(all(m['downloaded'] < m['total'] for m in progress))
        self.assertEqual(messages[-1]['event'], 'error')

    def test_many_small_updates_are_throttled_but_final_bytes_are_reported(self):
        self.env['NEURAL_FIXTURE_DOWNLOAD'] = 'throttled.bin'
        result, messages = self.run_runtime('--download')
        self.assertEqual(result.returncode, 0, result.stderr)
        progress = [m for m in messages if m['event'] == 'progress']
        self.assertGreaterEqual(len(progress), 2)
        self.assertLess(len(progress), 20)
        self.assertEqual(progress[-1]['downloaded'], 1000)


if __name__ == '__main__':
    unittest.main()
