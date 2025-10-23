'''Extract structured findings from free-text radiology reports.'''

from typing import Dict


def parse_report(report_text: str) -> Dict[str, str]:
    '''Placeholder parser that returns a trivial structure.'''
    return {'raw_text': report_text}
