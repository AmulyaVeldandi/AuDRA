'''Guideline retrieval pipeline.'''

from typing import List


def retrieve_guidelines(query: str, top_k: int = 5) -> List[str]:
    '''Run the RAG retrieval workflow and return matched guideline snippets.'''
    raise NotImplementedError('Implement end-to-end retrieval pipeline')
