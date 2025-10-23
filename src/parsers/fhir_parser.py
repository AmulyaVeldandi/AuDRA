'''Parse FHIR DiagnosticReport resources.'''

from typing import Any, Dict


def parse_diagnostic_report(resource: Dict[str, Any]) -> Dict[str, Any]:
    '''Simplified conversion of a FHIR resource into internal schema.'''
    return resource
