from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Generic, Type, TypeVar, get_args, get_origin

from util import JSONObject

M = TypeVar('M', bound=BaseModel)


class OpenAIFunction(Generic[M], ABC):
    """Represents a callable OpenAI function."""

    def _get_model_type(self) -> Type[BaseModel]:
        for base in type(self).__orig_bases__:
            origin = get_origin(base)
            if origin is None or not issubclass(origin, OpenAIFunction):
                continue
            return get_args(base)[0]
        raise Exception("Man, I dunno")

    def get_definition(self) -> JSONObject:
        """Returns the tool definition for this function."""
        return {
            'type': 'function',
            'function': {
                'name': self.get_name(),
                'description': self.get_description(),
                'parameters': self._get_model_type().model_json_schema()
            }
        }

    @abstractmethod
    def get_name(self) -> str:
        """Returns the name of this function."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Returns the description of this function."""
        pass

    @abstractmethod
    async def execute(self, arguments: M) -> str:
        """Executes the tool for the given arguments"""
        pass

    async def invoke(self, arguments: str) -> str:
        """Invokes this tool with the provided arguments"""
        return await self.execute(self._get_model_type().model_validate_json(arguments))
