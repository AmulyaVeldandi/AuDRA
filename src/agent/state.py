'''Agent state tracking utilities.'''

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentState:
    '''Captures the evolving reasoning trace for a report.'''

    thoughts: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
