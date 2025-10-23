'''Generate follow-up tasks based on guideline matches.'''

from typing import Dict, List


def build_tasks(matches: List[Dict[str, str]]) -> List[Dict[str, str]]:
    '''Map guideline matches into actionable follow-up tasks.'''
    raise NotImplementedError('Create structured follow-up task outputs')
