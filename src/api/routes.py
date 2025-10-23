'''API route definitions.'''

from uuid import uuid4

from fastapi import APIRouter, Request

from .models import ProcessReportRequest, ProcessReportResponse

router = APIRouter(prefix='/v1', tags=['reports'])


@router.post('/process_report', response_model=ProcessReportResponse)
async def process_report(
    payload: ProcessReportRequest, request: Request
) -> ProcessReportResponse:
    '''Process a radiology report and return structured follow-up insights.'''
    trace_id = getattr(request.state, 'trace_id', None) or str(uuid4())
    return ProcessReportResponse(tasks=[], guideline_hits=[], trace_id=trace_id)
