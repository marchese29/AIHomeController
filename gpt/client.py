import json
from openai import OpenAI
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from typing import Any, Dict, List

from gpt.functions import OpenAIFunction
from hubitat.client import DeviceEvent
from util import env_var


class OpenAISession:
    """Client wrapper for the OpenAI library"""

    def __init__(self):
        self._client = OpenAI(api_key=env_var('OPENAI_KEY'))
        self._gpt_model = env_var('GPT_MODEL')
        self._messages: List[Dict[str, Any]] = []
        self._functions: List[OpenAIFunction] = []
        self._function_map: Dict[str, OpenAIFunction] = {}

    def load_prompt(self, prompt: str):
        self._messages.append({'role': 'system', 'content': prompt})

    def load_functions(self, functions: List[OpenAIFunction]):
        self._functions = functions
        self._function_map = {f.get_name(): f for f in functions}

    async def handle_user_message(self, user_message: str) -> str:
        """Processes a message from the user, returns the response uttered by the LLM"""
        self._messages.append({'role': 'user', 'content': user_message})

        completion = self._run_completion()
        return await self._handle_response(completion.choices[0])

    async def handle_device_event(self, device_event: DeviceEvent):
        """Processes a device event"""
        self._messages.append({'role': 'user', 'content': f'Device Event: {device_event.model_dump_json()}'})

        completion = self._run_completion()
        print('Internal GPT Response: ' + await self._handle_response(completion.choices[0]))

    async def _handle_response(self, choice: Choice) -> str:
        match choice.finish_reason:
            case 'stop':
                return await self._handle_gpt_stop(choice)
            case 'tool_calls':
                return await self._handle_tool_calls(choice)
            case _:
                raise Exception(f"Don't recognize the '{choice.finish_reason}' finish_reason")

    async def _handle_gpt_stop(self, choice: Choice) -> str:
        self._messages.append({'role': choice.message.role, 'content': choice.message.content})
        return choice.message.content

    async def _handle_tool_calls(self, choice: Choice) -> str:
        self._messages.append({'role': choice.message.role, 'tool_calls': [
            {'id': tc.id, 'type': tc.type, 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}}
            for tc in choice.message.tool_calls]})
        for tool_call in choice.message.tool_calls:
            await self._handle_tool_call(tool_call)

        completion = self._run_completion()
        return await self._handle_response(completion.choices[0])

    async def _handle_tool_call(self, tool_call: ChatCompletionMessageToolCall):
        function = self._function_map[tool_call.function.name]
        result = await function.invoke(tool_call.function.arguments)

        self._messages.append({'tool_call_id': tool_call.id, 'role': 'tool', 'content': result})

    def _run_completion(self) -> ChatCompletion:
        return self._client.chat.completions.create(messages=self._messages,
                                                    tools=[f.get_definition() for f in self._functions],
                                                    model=self._gpt_model)
