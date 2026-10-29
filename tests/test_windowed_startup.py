import json
from pathlib import Path
import tempfile
import unittest
from startup_check import run_check

class WindowedStartupTests(unittest.TestCase):
    def test_actual_pos_health_with_no_console_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            run_check(path)
            result = json.loads(path.read_text())
            self.assertTrue(result['ok'], result.get('error'))
            self.assertEqual(result['health']['version'], '2.0.1')
            self.assertEqual(result['health']['protocol'], 2)
