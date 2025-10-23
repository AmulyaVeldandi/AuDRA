'''Pydantic models for request and response payloads.'''

from typing import List, Optional

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    '''Request body for processing a radiology report.'''

    report_text: str
    patient_id: Optional[str] = None


class FollowUpTask(BaseModel):
    '''Structured follow-up task returned by the agent.'''

    title: str
    description: str
    guideline_id: Optional[str] = None


class AgentResponse(BaseModel):
    '''Response payload emitted by the agent pipeline.'''

    status: str
    message: str
    tasks: List[FollowUpTask] = Field(default_factory=list)
