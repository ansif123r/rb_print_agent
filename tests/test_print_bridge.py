import base64
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch, Mock

from print_bridge import PrintService, default_format

class Immediate:
    def submit(self, fn, *args): fn(*args)

class Deferred:
    def __init__(self): self.jobs = []
    def submit(self, *args): self.jobs.append(args)

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Mock()
        self.manager = Mock()
        self.manager.list_printers.return_value = [SimpleNamespace(name=n) for n in ['POS80 Printer', 'Second Thermal', 'Office Laser', 'Microsoft Print to PDF']]
        self.manager.driver_name.return_value = 'Printer Driver'
        self.service = PrintService(self.temp.name, lambda: self.manager, lambda: self.engine, executor=Immediate())

    def submit(self, printer='Office Laser', kind='A4 Tax Invoice', data=b'%PDF-test', id=None):
        prefix = 'RBRAW1:' if kind == 'Thermal Receipt' else 'RBA4PDF1:'
        return self.service.submit(id or str(uuid4()), printer, kind, 'INV-1', prefix + base64.b64encode(data).decode())

    def test_selected_a4_device_receives_pdf_not_raw(self):
        self.service.select('Office Laser', 'A4 Tax Invoice')
        result = self.submit()
        self.assertEqual(result['state'], 'printed')
        self.engine.print_a4_pdf.assert_called_once_with('Office Laser', b'%PDF-test', 'INV-1')
        self.engine.raw_bytes.assert_not_called()
        self.assertEqual(self.service.printers()['printer_name'], 'Office Laser')

    def test_exact_thermal_bytes_to_selected_device(self):
        result = self.submit('Second Thermal', 'Thermal Receipt', b'\x1b@\xff\x00')
        self.assertEqual(result['state'], 'printed')
        self.engine.raw_bytes.assert_called_once_with('Second Thermal', b'\x1b@\xff\x00')
        self.engine.print_a4_pdf.assert_not_called()

    def test_pdf_save_and_cancel_do_not_spool(self):
        path = Path(self.temp.name) / 'invoice.pdf'
        self.service.save_dialog = lambda title: str(path)
        self.assertEqual(self.submit('Microsoft Print to PDF')['state'], 'saved')
        self.assertEqual(path.read_bytes(), b'%PDF-test')
        self.service.save_dialog = lambda title: None
        self.assertEqual(self.submit('Microsoft Print to PDF')['state'], 'cancelled')
        self.assertEqual(self.engine.mock_calls, [])

    def test_retry_same_id_prints_once_and_rejects_changed_content(self):
        id = str(uuid4())
        self.submit(id=id); self.submit(id=id)
        self.engine.print_a4_pdf.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'different content'): self.submit(id=id, data=b'%PDF-different')

    def test_missing_device_never_falls_back(self):
        self.service.select('Office Laser', 'A4 Tax Invoice')
        self.manager.list_printers.return_value = [SimpleNamespace(name='POS80 Printer')]
        self.assertFalse(self.service.printers()['available'])
        with self.assertRaisesRegex(ValueError, 'not installed'): self.submit()
        self.assertEqual(self.engine.mock_calls, [])

    def test_format_validation_and_preferences(self):
        self.assertEqual(default_format('80mm USB'), 'Thermal Receipt')
        self.assertEqual(default_format('Office Laser'), 'A4 Tax Invoice')
        with self.assertRaisesRegex(ValueError, 'requires A4'): self.service.select('Microsoft Print to PDF', 'Thermal Receipt')
        self.service.select('Second Thermal', 'Thermal Receipt')
        self.service.select('Office Laser', 'A4 Tax Invoice')
        devices = {p['name']: p['format'] for p in self.service.printers()['printers']}
        self.assertEqual(devices['Second Thermal'], 'Thermal Receipt')

    def test_failure_after_spool_is_unknown_not_auto_replayed(self):
        self.engine.print_a4_pdf.side_effect = RuntimeError('Lost spool response')
        id = str(uuid4()); self.assertEqual(self.submit(id=id)['state'], 'unknown')
        self.submit(id=id)
        self.engine.print_a4_pdf.assert_called_once()

    def test_restart_does_not_replay_incomplete_jobs(self):
        self.service.executor = Deferred()
        queued = self.submit()
        printing = self.submit(); self.service._state(printing['id'], 'printing')
        restarted = PrintService(self.temp.name, lambda: self.manager, lambda: self.engine, executor=Immediate())
        self.assertEqual(restarted.job(queued['id'])['state'], 'failed')
        self.assertEqual(restarted.job(printing['id'])['state'], 'unknown')
        self.assertEqual(self.engine.mock_calls, [])

    def test_job_destination_survives_selection_change(self):
        executor = Deferred(); self.service.executor = executor
        job = self.submit()
        self.service.select('POS80 Printer', 'Thermal Receipt')
        fn, *args = executor.jobs[0]; fn(*args)
        self.engine.print_a4_pdf.assert_called_once_with('Office Laser', b'%PDF-test', 'INV-1')

class ApiTests(unittest.TestCase):
    setUp = BridgeTests.setUp
    def test_origin_host_and_session_boundary(self):
        import api
        from fastapi.testclient import TestClient
        api.app.state.print_service = self.service
        with patch.object(api, 'allowed_origin', return_value='https://shop.example'):
            with TestClient(api.app, base_url='http://127.0.0.1:8766') as client:
                self.assertNotIn('session_token', client.get('/health').json())
                headers = {'Origin': 'https://shop.example'}
                token = client.get('/health', headers=headers).json()['session_token']
                self.assertEqual(client.get('/printers', headers=headers).status_code, 403)
                headers['X-RB-Print-Session'] = token
                self.assertEqual(client.get('/printers', headers=headers).status_code, 200)
                self.assertEqual(client.get('/printers', headers={**headers, 'Origin': 'https://evil.example'}).status_code, 403)
                self.assertEqual(client.get('/health', headers={**headers, 'Host': 'evil.example:8766'}).status_code, 403)
                self.assertEqual(client.options('/jobs', headers=headers).headers['access-control-allow-private-network'], 'true')
                self.assertEqual(client.post('/printers/select', headers=headers, json={'printer_name': 'Office Laser', 'print_format': 'A4 Tax Invoice'}).status_code, 200)
                self.assertEqual(self.service.printers()['printer_name'], 'Office Laser')

if __name__ == '__main__': unittest.main()

class EngineTests(unittest.TestCase):
    def test_a4_uses_selected_windows_driver_and_closes_handles(self):
        import sys
        from print_engine import PrintEngine
        engine = object.__new__(PrintEngine)
        engine._win32print = Mock()
        mode = SimpleNamespace(Fields=0)
        engine._win32print.GetPrinter.return_value = {'pDevMode': mode}
        engine._win32print.DocumentProperties.return_value = 1
        dc = Mock(); dc.GetDeviceCaps.return_value = 2400
        gui = Mock(); ui = Mock(); ui.CreateDCFromHandle.return_value = dc
        con = SimpleNamespace(DMPAPER_A4=9, DMORIENT_PORTRAIT=1, DM_PAPERSIZE=2, DM_ORIENTATION=1,
            DM_PAPERLENGTH=4,DM_PAPERWIDTH=8,DM_IN_BUFFER=8,DM_OUT_BUFFER=2,HORZRES=8,VERTRES=10)
        import fitz
        pdf = fitz.open(); pdf.new_page(); raw=pdf.tobytes(); pdf.close()
        with patch.dict(sys.modules, {'win32con':con,'win32gui':gui,'win32ui':ui}), patch('PIL.ImageWin.Dib') as dib:
            engine.print_a4_pdf('Office Laser',raw,'INV-1')
        engine._win32print.OpenPrinter.assert_called_once_with('Office Laser')
        gui.CreateDC.assert_called_once_with('WINSPOOL','Office Laser',mode)
        self.assertEqual(mode.PaperSize,9)
        dc.StartDoc.assert_called_once_with('INV-1')
        dc.EndDoc.assert_called_once();dc.DeleteDC.assert_called_once()
        engine._win32print.ClosePrinter.assert_called_once()
        dib.return_value.draw.assert_called_once()
