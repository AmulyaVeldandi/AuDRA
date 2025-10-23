'''FHIR/HL7 integration client (mock implementation).'''

from typing import Any, Dict


class EHRClient:
    '''Provides simplified access to patient context for demos.'''

    def fetch_patient(self, patient_id: str) -> Dict[str, Any]:
        '''Retrieve mock patient demographics.'''
        return {"id": patient_id, "name": "Demo Patient"}
