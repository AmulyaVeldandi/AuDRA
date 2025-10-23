'''Input validation utilities.'''

from typing import Iterable


def ensure_non_empty(values: Iterable[str]) -> None:
    '''Raise a ValueError if any strings are empty.'''
    if any(not value for value in values):
        raise ValueError('Inputs must be non-empty strings')
