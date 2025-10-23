'''Client for the NVIDIA Retrieval Embedding NIM.'''

from typing import List


class NimEmbeddingClient:
    '''Generates embeddings for texts used in retrieval.'''

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def embed(self, texts: List[str]) -> List[List[float]]:
        '''Return vector representations for the supplied texts.'''
        raise NotImplementedError('Connect to the embedding NIM endpoint')
