'''Match parsed findings to guideline criteria.'''

from typing import Dict, List


def match_findings(findings: Dict[str, str]) -> List[Dict[str, str]]:
    '''Return relevant guideline recommendations for the supplied findings.'''
    raise NotImplementedError('Implement guideline matching heuristics')
