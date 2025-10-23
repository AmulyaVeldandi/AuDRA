'''Vector store abstraction layer.'''

from typing import List, Tuple


class VectorStore:
    '''Simple interface for similarity search requests.'''

    def __init__(self, client: object) -> None:
        self.client = client

    def search(self, embedding: List[float], top_k: int = 5) -> List[Tuple[str, float]]:
        '''Return the most similar guideline chunks.'''
        raise NotImplementedError('Integrate with OpenSearch or Pinecone')
