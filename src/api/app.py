'''FastAPI application for the AuDRA-Rad service.'''

from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title='AuDRA-Rad API',
    description='Autonomous Radiology Follow-up Assistant',
    version='0.1.0',
)

app.include_router(router)


@app.get('/healthz')
async def health_check() -> dict:
    '''Simple readiness endpoint.'''
    return {'status': 'ok'}
