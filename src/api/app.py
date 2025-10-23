'''FastAPI application for the AuDRA-Rad service.'''

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Callable, Awaitable

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore[assignment]

from fastapi import FastAPI, Request, Response

from ..utils.logger import get_logger
from .routes import router


def _load_version() -> str:
    pyproject_path = Path('pyproject.toml')
    if not pyproject_path.exists():
        return '0.1.0'

    try:
        data = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))
    except (tomllib.TOMLDecodeError, OSError):
        return '0.1.0'

    return data.get('project', {}).get('version', '0.1.0')


APP_VERSION = _load_version()

app = FastAPI(title='AuDRA-Rad', version=APP_VERSION)

logger = get_logger(__name__)


@app.middleware('http')
async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    '''Attach a trace identifier and emit structured JSON logs for each request.'''

    trace_id = request.headers.get('x-trace-id') or str(uuid.uuid4())
    request.state.trace_id = trace_id
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        duration = time.perf_counter() - start_time
        logger.exception(
            json.dumps(
                {
                    'event': 'request_error',
                    'trace_id': trace_id,
                    'method': request.method,
                    'path': request.url.path,
                    'duration_ms': round(duration * 1000, 2),
                }
            )
        )
        raise

    duration = time.perf_counter() - start_time
    logger.info(
        json.dumps(
            {
                'event': 'request_complete',
                'trace_id': trace_id,
                'method': request.method,
                'path': request.url.path,
                'status_code': status_code,
                'duration_ms': round(duration * 1000, 2),
            }
        )
    )

    response.headers.setdefault('X-Trace-Id', trace_id)
    return response


app.include_router(router)


@app.get('/healthz', tags=['system'])
async def health_check() -> dict[str, str]:
    '''Simple readiness endpoint.'''
    return {'status': 'ok'}


@app.get('/version', tags=['system'])
async def version() -> dict[str, str]:
    '''Return the service version derived from pyproject or fallback.'''
    return {'version': APP_VERSION}
