'''Client for the Nemotron NIM large language model service.'''

from typing import Any


class NimLLMClient:
    '''Thin wrapper around the Nemotron NIM Inference API.'''

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def generate(self, prompt: str, **kwargs: Any) -> str:
        '''Submit a prompt to the hosted LLM and return the response.'''
        raise NotImplementedError('Wire up HTTP calls to Nemotron NIM')
