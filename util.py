import os
import sys
from typing import Dict, List, Optional, Union

JSON = Union[int, float, str, bool, None, Dict[str, 'JSON'], List['JSON']]
JSONObject = Dict[str, JSON]
JSONList = List[JSON]


def env_var(name: str, allow_null: bool = False) -> Optional[str]:
    """A useful utility for validating the presence of an environment variable before loading"""
    if not allow_null and name not in os.environ:
        sys.exit(f'{name} was not set in the environment')
    value = os.environ[name]
    if not allow_null and value is None:
        sys.exit(f'The value of {name} in the environment cannot be empty')
    return value
