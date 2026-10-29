"""Uvicorn configuration for a frozen, console-free Windows desktop process."""
import uvicorn


def create_server(app, host, port):
    # PyInstaller --windowed sets stdout/stderr to None. Uvicorn's default
    # colour formatter calls stdout.isatty() and otherwise prevents startup.
    # Explicit protocol modules also avoid optional runtime discovery in the EXE.
    return uvicorn.Server(uvicorn.Config(
        app, host=host, port=port, log_level='warning', log_config=None,
        access_log=False, use_colors=False, loop='asyncio', http='h11',
        ws='none', lifespan='on',
    ))
