'''Composite deployment script for SageMaker endpoints.'''

from . import nim_embedding_endpoint, nim_llm_endpoint


def deploy_all() -> None:
    '''Deploy both Nemotron endpoints.'''
    nim_llm_endpoint.deploy_nim_llm()
    nim_embedding_endpoint.deploy_nim_embedding()
