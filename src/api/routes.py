'''API route definitions.'''

from fastapi import APIRouter

from .models import AgentResponse, ReportRequest

router = APIRouter(prefix='/api', tags=['reports'])


@router.post('/reports', response_model=AgentResponse)
async def process_report(request: ReportRequest) -> AgentResponse:
    '''Placeholder endpoint for processing radiology reports.'''
    return AgentResponse(status='pending', message='Processing not yet implemented')
