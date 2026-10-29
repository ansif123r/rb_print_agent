# RB Print Agent

Windows desktop print bridge for R B FRESH MART. It connects ERPNext to local Windows thermal printers and prints queued receipts without opening a browser print dialog.

## Desktop installation

The recommended deployment is the Windows installer produced by GitHub Actions:

- `RB-Print-Agent-Setup-1.0.0.exe`
- Windows 10/11 x64-compatible systems
- No Python installation required
- No Git installation required
- Starts automatically with Windows
- Stores the ERPNext token in the Windows machine's protected configuration
- Detects installed Windows printers
- Provides Test Connection and Test Printer actions

After installation, open **RB Print Agent** from the Start Menu if setup is required. Enter the ERPNext URL, RB Print token and the local printer name. The agent then runs in the background and polls the ERPNext RB Print Queue.

## Development mode

Python 3.11+ can still be used for development:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

The local API is available at `http://127.0.0.1:8765`.

### Check health

Open `http://127.0.0.1:8765/health`.

### List printers

Open `http://127.0.0.1:8765/printers`.

### Test print

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/test-print `
  -ContentType 'application/json' `
  -Body '{"printer":"YOUR WINDOWS PRINTER NAME"}'
```

The default test uses ESC/POS raw commands for supported thermal receipt printers.


## Version 2.0: select the actual device in POS

RB Print Agent handles printing. The separate Local POS Controller continues to
handle offline sales on port 8765. The Print Agent browser bridge uses **8766**.

Install this version on the cashier's Windows desktop and update the ERP app's
`feature/rb-print-queue` branch, build assets, then reload POS. Keep the existing
ERP URL/token settings. In POS choose **Receipt Printer**, choose an installed
Windows device, and save its format:

- **Thermal Receipt**: the existing raster receipt, including Malayalam, sent as
  ESC/POS to the exact selected receipt printer.
- **A4 Tax Invoice**: the submitted invoice's HSN, saved GST details and totals.
  Regular printers use their Windows driver with A4 portrait paper.
- **Microsoft Print to PDF**: A4 is required. A Save PDF dialog opens in the logged-in
  Windows session and saves the original generated PDF. Cancelling does not spool
  another receipt. This path intentionally saves the PDF directly, preserving text
  and fonts instead of rasterising it through the Microsoft driver.

Unknown printer models default to A4. For a new ESC/POS receipt printer, choose
Thermal Receipt once. Choices persist per Windows user, independently of the
Windows default printer. A missing selected device produces a message and never
falls back to POS80. The existing offline controller's receipt configuration is
independent; this update routes submitted ERP invoices from the online POS screen.

The browser requests a read-only render from ERP and submits a UUID to the local
agent. New POS prints do not create a second cloud queue job. The local SQLite
journal deduplicates retries and never automatically replays uncertain jobs after
an agent restart. If delivery is uncertain, check the output before deliberately
reprinting. A successful spool means Windows accepted the job; it cannot prove
paper physically emerged from an offline or jammed printer.

The local API binds only to loopback, checks the configured ERP origin/Host and
requires a per-process session token. Allow local network access for the ERP site
if your browser asks. ERP credentials remain in the desktop configuration.

Installer upgrades retain settings, remove the old duplicate Startup shortcut and
keep one login startup entry. Quit any old running Print Agent before upgrading.
Do not replace or uninstall the Local POS Controller for this printing update.

Validation: `python -m unittest discover -s tests -v` (install `httpx` for API tests).
Physical printer output and the Save As dialog should be checked on the POS PC
once after installation, using POS80, another printer, and Microsoft Print to PDF.
