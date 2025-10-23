'''Structured logging helpers.'''

import logging
from typing import Optional


def configure_logging(level: int = logging.INFO) -> None:
    '''Configure the root logger with a structured format.'''
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )


def get_logger(name: Optional[str] = None) -> logging.Logger:
    '''Return a logger configured for the application.'''
    if not logging.getLogger().handlers:
        configure_logging()
    return logging.getLogger(name or 'audra_rad')
