"""Packaging smoke check: no credentials, queue polling, or physical printing."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback

import requests


def run_check(result_path):
    server = None
    thread = None
    result = {'ok': False}
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        # Match the actual PyInstaller --windowed environment, even in unit tests.
        sys.stdout = sys.stderr = None
        from api import app, settings
        from local_server import create_server
        from print_bridge import PrintService
        with tempfile.TemporaryDirectory() as directory:
            app.state.print_service = PrintService(directory)
            server = create_server(app, settings.host, settings.port)
            failures = []
            def serve():
                try: server.run()
                except BaseException as exc: failures.append(str(exc))
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                if failures: raise RuntimeError(failures[0])
                if not thread.is_alive(): raise RuntimeError('Local server exited before listening.')
                if time.monotonic() > deadline: raise TimeoutError('Local server did not start.')
                time.sleep(.05)
            session = requests.Session(); session.trust_env = False
            response = session.get(f'http://{settings.host}:{settings.port}/health', timeout=5)
            response.raise_for_status()
            health = response.json()
            if health.get('protocol') != 2 or health.get('version') != settings.version:
                raise RuntimeError('Unexpected local health response.')
            result = {'ok': True, 'health': health}
            server.should_exit = True
            thread.join(5)
            if thread.is_alive(): raise RuntimeError('Local server did not shut down.')
    except BaseException:
        result = {'ok': False, 'error': traceback.format_exc()}
    finally:
        if server: server.should_exit = True
        if thread: thread.join(5)
        sys.stdout, sys.stderr = original_stdout, original_stderr
        Path(result_path).write_text(json.dumps(result), encoding='utf-8')
