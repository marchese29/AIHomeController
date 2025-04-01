import json
import os
import sys
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

import aiofiles

JSON = Union[int, float, str, bool, None, "JSONObject", "JSONList"]
JSONObject = Dict[str, JSON]
JSONList = List[JSON]

# Type for any model with model_dump method
ModelT = TypeVar("ModelT", bound=Any)


def env_var(name: str, allow_null: bool = False) -> Optional[str]:
    """A useful utility for validating the presence of an environment variable before
    loading"""
    if not allow_null and name not in os.environ:
        sys.exit(f"{name} was not set in the environment")
    if allow_null and name not in os.environ:
        return None
    value = os.environ[name]
    if not allow_null and value is None:
        sys.exit(f"The value of {name} in the environment cannot be empty")
    return value


async def save_models_to_json(models: Sequence[ModelT], filepath: str) -> None:
    """Save a sequence of Pydantic models to a JSON file.

    Args:
        models: Sequence of models with model_dump method
        filepath: Path to save the JSON file

    Raises:
        RuntimeError: If the file cannot be written
    """
    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(
                json.dumps([model.model_dump() for model in models], indent=2)
            )
    except (IOError, OSError) as e:
        raise RuntimeError(f"Failed to save models to {filepath}: {e}") from e


async def load_models_from_json(
    model_class: Type[ModelT], filepath: str, verbose: bool = True
) -> list[ModelT]:
    """Load a sequence of Pydantic models from a JSON file.

    Args:
        model_class: The class to validate model data against
        filepath: Path to the JSON file
        verbose: Whether to print status messages (default True)

    Returns:
        List of validated models, or empty list if file doesn't exist
    """
    if not os.path.exists(filepath):
        return []

    try:
        if verbose:
            print(f"Loading models from {filepath}")

        async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
            content = await f.read()
            models_data = json.loads(content)
            models = []

            for model_data in models_data:
                if verbose:
                    name = model_data.get("name", str(model_data))
                    print(f"Loading model: {name}")
                models.append(model_class.model_validate(model_data))

            return models

    except (IOError, OSError) as e:
        print(f"Failed to read models from {filepath}: {e}")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in file {filepath}: {e}")
    except Exception as e:
        print(f"Error loading models from {filepath}: {e}")

    return []
