'''Configuration helpers using environment variables.'''

from pydantic import BaseSettings


class Settings(BaseSettings):
    '''Global application settings.'''

    app_name: str = 'AuDRA-Rad'
    nim_llm_endpoint: str = 'http://localhost:8001'
    nim_embedding_endpoint: str = 'http://localhost:8002'

    class Config:
        env_file = '.env'


settings = Settings()
