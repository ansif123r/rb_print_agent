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
