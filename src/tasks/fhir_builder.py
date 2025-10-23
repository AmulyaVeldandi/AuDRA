'''Construct FHIR ServiceRequest payloads.'''

from typing import Any, Dict


def build_service_request(task: Dict[str, Any]) -> Dict[str, Any]:
    '''Convert an internal task representation into FHIR ServiceRequest.'''
    raise NotImplementedError('Translate tasks into FHIR resources')
