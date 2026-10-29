"""Browser bridge for the configured ERP origin, separate from offline POS."""
from __future__ import annotations

import secrets
import threading
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from config import settings
from print_bridge import PrintService, MAX_PAYLOAD

app = FastAPI(title=settings.app_name, version=settings.version, docs_url=None, redoc_url=None)


_service_lock = threading.Lock()

def service():
    with _service_lock:
        if not getattr(app.state, 'print_service', None):
            app.state.print_service = PrintService()
        return app.state.print_service


def allowed_origin():
    url = urlsplit(settings.erpnext_url)
    return f'{url.scheme}://{url.netloc}' if url.scheme in ('https', 'http') and url.netloc else ''


@app.middleware('http')
async def browser_boundary(request: Request, call_next):
    origin = request.headers.get('origin', '')
    if request.headers.get('host') not in (f'127.0.0.1:{settings.port}', f'localhost:{settings.port}'):
        return JSONResponse({'detail': 'Invalid local agent host.'}, status_code=403)
    if origin and origin != allowed_origin():
        return JSONResponse({'detail': 'This website is not paired with RB Print Agent.'}, status_code=403)
    if request.method == 'OPTIONS':
        response = Response(status_code=204)
    elif request.url.path == '/health' and request.method == 'GET':
        response = await call_next(request)
    else:
        token = request.headers.get('x-rb-print-session', '')
        if not origin or not secrets.compare_digest(token, service().session_token):
            return JSONResponse({'detail': 'Refresh the POS printer connection.'}, status_code=403,
                                headers={'Access-Control-Allow-Origin': origin} if origin else None)
        if request.method == 'POST':
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': 'JSON is required.'}, status_code=415)
            try: length = int(request.headers.get('content-length') or 0)
            except ValueError: length = MAX_PAYLOAD + 8193
            if length > MAX_PAYLOAD + 8192:
                return JSONResponse({'detail': 'Print data exceeds the limit.'}, status_code=413)
        response = await call_next(request)
    if origin:
        response.headers.update({'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, X-RB-Print-Session',
            'Access-Control-Allow-Private-Network': 'true', 'Vary': 'Origin'})
    response.headers['Cache-Control'] = 'no-store'
    return response


class Selection(BaseModel):
    printer_name: str = Field(min_length=1, max_length=255)
    print_format: str


class PrintRequest(Selection):
    request_id: str
    title: str = Field(min_length=1, max_length=140)
    payload: str = Field(min_length=1, max_length=MAX_PAYLOAD)


@app.get('/health')
def health(request: Request):
    result = {'app': settings.app_name, 'version': settings.version, 'protocol': 2}
    if request.headers.get('origin') == allowed_origin() and allowed_origin():
        result['session_token'] = service().session_token
    return result


@app.get('/printers')
def printers():
    try: return service().printers()
    except Exception as exc: raise HTTPException(400, str(exc)) from exc


@app.post('/printers/select')
def select(request: Selection):
    try: return service().select(request.printer_name, request.print_format)
    except Exception as exc: raise HTTPException(400, str(exc)) from exc


@app.post('/jobs')
def print_job(request: PrintRequest):
    try:
        return service().submit(request.request_id, request.printer_name, request.print_format, request.title, request.payload)
    except (ValueError, TypeError) as exc: raise HTTPException(400, str(exc)) from exc


@app.get('/jobs/{request_id}')
def job_status(request_id: str):
    value = service().job(request_id)
    if value is None: raise HTTPException(404, 'Print request has not reached this agent.')
    return value
