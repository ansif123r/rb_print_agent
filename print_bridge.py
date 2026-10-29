"""Per-terminal printer choices and durable, non-replaying local print jobs."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import uuid

from config_store import load_config
from print_engine import PrintEngine
from printer_manager import PrinterManager

FORMATS = {'Thermal Receipt', 'A4 Tax Invoice'}
MAX_PAYLOAD = 40 * 1024 * 1024


def data_directory():
    return Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'RB Print Agent'


def is_pdf_printer(name, driver=''):
    return 'microsoft print to pdf' in (name + ' ' + driver).casefold()


def default_format(name):
    # Unknown devices use A4. A new receipt printer can be assigned once in POS.
    if re.search(r'pos\s*[-_]?\s*(58|80)|thermal|receipt|\b(?:58|80)\s*mm|\btm[- ]', name, re.I):
        return 'Thermal Receipt'
    return 'A4 Tax Invoice'


class PrintService:
    def __init__(self, directory=None, manager_factory=PrinterManager,
                 engine_factory=PrintEngine, save_dialog=None, executor=None):
        self.directory = Path(directory or data_directory())
        self.directory.mkdir(parents=True, exist_ok=True)
        self.preferences_file = self.directory / 'printer_preferences.json'
        self.database = self.directory / 'print_jobs.sqlite3'
        self.manager_factory = manager_factory
        self.engine_factory = engine_factory
        self.save_dialog = save_dialog
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix='rb-print')
        self.lock = threading.RLock()
        self.session_token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, printer TEXT NOT NULL,
                format TEXT NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '', created TEXT DEFAULT CURRENT_TIMESTAMP)''')
            # Never replay after a crash: a Printing job may have reached paper.
            db.execute("UPDATE jobs SET state='unknown', detail='Agent restarted during printing. Check the output before deliberately reprinting.' WHERE state='printing'")
            db.execute("UPDATE jobs SET state='failed', detail='Agent restarted before this job began printing.' WHERE state='queued'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def preferences(self):
        if self.preferences_file.exists():
            value = json.loads(self.preferences_file.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError('Printer settings are invalid. Select the printer again.')
            return value
        return {'printer_name': load_config().get('printer_name') or 'POS80 Printer', 'formats': {}}

    def printers(self):
        manager = self.manager_factory()
        installed = manager.list_printers()
        with self.lock:
            preferences = self.preferences()
        selected = preferences.get('printer_name', '')
        formats = preferences.get('formats') or {}
        return {'printers': [{'name': p.name, 'format': formats.get(p.name) or default_format(p.name)} for p in installed],
                'printer_name': selected, 'format': formats.get(selected) or default_format(selected),
                'available': any(p.name == selected for p in installed)}

    def select(self, name, print_format):
        self.validate_printer(name, print_format)
        with self.lock:
            current = self.preferences()
            current['printer_name'] = name
            current.setdefault('formats', {})[name] = print_format
            temporary = self.preferences_file.with_suffix('.tmp')
            temporary.write_text(json.dumps(current, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary, self.preferences_file)
        return self.printers()

    def validate_printer(self, name, print_format):
        if print_format not in FORMATS:
            raise ValueError('Choose Thermal Receipt or A4 Tax Invoice.')
        if not any(p.name == name for p in self.manager_factory().list_printers()):
            raise ValueError(f"Selected printer '{name}' is not installed. Choose another printer in POS.")
        if is_pdf_printer(name) and print_format != 'A4 Tax Invoice':
            raise ValueError('Microsoft Print to PDF requires A4 Tax Invoice.')

    def job(self, request_id):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT id, printer, format, title, state, detail FROM jobs WHERE id=?', (request_id,)).fetchone()
            return dict(row) if row else None

    def submit(self, request_id, printer_name, print_format, title, payload):
        if str(uuid.UUID(request_id)) != request_id:
            raise ValueError('Invalid print request identifier.')
        if not isinstance(payload, str) or len(payload) > MAX_PAYLOAD:
            raise ValueError('Print data is too large or invalid.')
        prefix = 'RBRAW1:' if print_format == 'Thermal Receipt' else 'RBA4PDF1:'
        if not payload.startswith(prefix):
            raise ValueError('The invoice format does not match the selected printer format.')
        raw = base64.b64decode(payload[len(prefix):], validate=True)
        if not raw or (print_format == 'A4 Tax Invoice' and not raw.startswith(b'%PDF-')):
            raise ValueError('The print document is empty or invalid.')
        self.validate_printer(printer_name, print_format)
        fingerprint = hashlib.sha256(json.dumps([printer_name, print_format, title, payload]).encode()).hexdigest()
        with self.lock, self.connect() as db:
            existing = db.execute('SELECT fingerprint FROM jobs WHERE id=?', (request_id,)).fetchone()
            if existing:
                if existing[0] != fingerprint:
                    raise ValueError('This print request already exists with different content.')
                return self.job(request_id)
            db.execute('INSERT INTO jobs(id,fingerprint,printer,format,title,state) VALUES(?,?,?,?,?,?)',
                       (request_id, fingerprint, printer_name, print_format, title[:140], 'queued'))
        # Only this insertion queues work. Retries with the same ID never spool again.
        try:
            self.executor.submit(self._run, request_id, raw)
        except Exception as exc:
            self._state(request_id, 'failed', str(exc))
        return self.job(request_id)

    def _state(self, request_id, state, detail=''):
        with self.connect() as db:
            db.execute('UPDATE jobs SET state=?, detail=? WHERE id=?', (state, str(detail)[:1000], request_id))

    def _run(self, request_id, raw):
        row = self.job(request_id)
        started = False
        try:
            self.validate_printer(row['printer'], row['format'])
            engine = self.engine_factory()
            driver = self.manager_factory().driver_name(row['printer'])
            if is_pdf_printer(row['printer'], driver):
                if row['format'] != 'A4 Tax Invoice':
                    raise ValueError('This PDF printer requires A4 Tax Invoice.')
                if self.save_dialog is None:
                    raise ValueError('Start RB Print Agent from the Windows Start Menu to save a PDF.')
                path = self.save_dialog(row['title'])
                if not path:
                    self._state(request_id, 'cancelled', 'PDF saving was cancelled.'); return
                # Save the original generated PDF, preserving selectable text/fonts.
                destination = Path(path)
                temporary = destination.with_name(destination.name + '.' + request_id + '.tmp')
                try:
                    temporary.write_bytes(raw)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
                self._state(request_id, 'saved', destination.name); return
            self._state(request_id, 'printing'); started = True
            if row['format'] == 'Thermal Receipt':
                engine.raw_bytes(row['printer'], raw)
            else:
                engine.print_a4_pdf(row['printer'], raw, row['title'])
            self._state(request_id, 'printed')
        except Exception as exc:
            self._state(request_id, 'unknown' if started else 'failed',
                        (str(exc) + ' Check the printer before reprinting.') if started else str(exc))
