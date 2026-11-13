import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import media_tools


class MediaToolsTests(unittest.TestCase):
    def test_prefers_available_system_ffmpeg(self):
        with patch('media_tools.shutil.which', return_value='/tools/ffmpeg'):
            self.assertEqual(media_tools.ffmpeg_executable(), '/tools/ffmpeg')

    def test_resolves_bundled_ffmpeg_when_path_is_missing(self):
        module = types.SimpleNamespace(get_ffmpeg_exe=lambda: '/bundle with spaces/ffmpeg')
        with patch('media_tools.shutil.which', return_value=None), \
                patch.dict('sys.modules', {'imageio_ffmpeg': module}):
            self.assertEqual(media_tools.ffmpeg_executable(), '/bundle with spaces/ffmpeg')

    def test_missing_ffmpeg_reports_cross_platform_install_hint(self):
        with patch('media_tools.shutil.which', return_value=None), \
                patch.dict('sys.modules', {'imageio_ffmpeg': None}):
            with self.assertRaisesRegex(RuntimeError, 'requirements-desktop'):
                media_tools.ffmpeg_executable()

    def test_finds_windows_espeak_in_program_files(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'eSpeak NG' / 'espeak-ng.exe'
            executable.parent.mkdir()
            executable.touch()
            with patch('media_tools.shutil.which', return_value=None), \
                    patch('media_tools.current_platform', return_value='win32'), \
                    patch.dict('os.environ', {'ProgramFiles': directory}):
                self.assertEqual(media_tools.espeak_executable(), str(executable))


if __name__ == '__main__':
    unittest.main()
