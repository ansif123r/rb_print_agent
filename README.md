# RB Device Agent

Windows device bridge for R B FRESH MART, starting with direct USB/Windows printer support.

## Milestone 1

- Detect installed Windows printers.
- Expose a local HTTP API on `127.0.0.1:8765`.
- Provide an ESC/POS test-print endpoint.
- Provide a RAW text printing endpoint.
- Keep the printer layer independent from future ERPNext communication.

## Run on Windows

Requirements:

- Windows 10/11
- Python 3.11+

Create the environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start the agent:

```powershell
python app.py
```

The local API is available at `http://127.0.0.1:8765`.

### Check health

Open:

`http://127.0.0.1:8765/health`

### List printers

Open:

`http://127.0.0.1:8765/printers`

### Test print

PowerShell example:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/test-print `
  -ContentType 'application/json' `
  -Body '{"printer":"YOUR WINDOWS PRINTER NAME"}'
```

The default test uses ESC/POS raw commands, which is appropriate for supported thermal receipt printers.
