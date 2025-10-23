'''Utility tools exposed to the agent for retrieval and validation.'''

from typing import Any, Dict


class ToolRegistry:
    '''Registers callable tools that the agent can invoke.'''

    def __init__(self) -> None:
        self._tools: Dict[str, Any] = {}

    def register(self, name: str, tool: Any) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> Any:
        return self._tools[name]
