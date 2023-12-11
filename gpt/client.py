import json
from openai import OpenAI
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from typing import Any, Dict, List

from util import env_var


class OpenAISession:
    """Client wrapper for the OpenAI library"""

    def __init__(self):
        self._client = OpenAI(api_key=env_var('OPENAI_KEY'))
        self._gpt_model = env_var('GPT_MODEL')
        self._messages: List[Dict[str, Any]] = []

    def load_prompt(self, prompt: str):
        self._messages.append({'role': 'system', 'content': prompt})

    async def handle_user_message(self, user_message: str, tools: List[ChatCompletionToolParam] = None) -> str:
        """Processes a message from the user, returns the response uttered by the LLM"""
        self._messages.append({'role': 'user', 'content': user_message})

        all_tools = [] if tools is None else tools
        completion = self._client.chat.completions.create(messages=self._messages, tools=all_tools,
                                                          model=self._gpt_model)
        return await self._handle_response(completion.choices[0], all_tools)

    async def _handle_response(self, choice: Choice, tools: List[ChatCompletionToolParam]) -> str:
        match choice.finish_reason:
            case 'stop':
                return await self._handle_gpt_stop(choice)
            case 'tool_calls':
                return await self._handle_tool_calls(choice, tools)
            case _:
                raise Exception(f"Don't recognize the '{choice.finish_reason}' finish_reason")

    async def _handle_gpt_stop(self, choice: Choice) -> str:
        self._messages.append({'role': choice.message.role, 'content': choice.message.content})
        return choice.message.content

    async def _handle_tool_calls(self, choice: Choice, tools: List[ChatCompletionToolParam]) -> str:
        self._messages.append({'role': choice.message.role, 'tool_calls': [
            {'id': tc.id, 'type': tc.type, 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}}
            for tc in choice.message.tool_calls]})
        for tool_call in choice.message.tool_calls:
            await self._handle_tool_call(tool_call)

        completion = self._client.chat.completions.create(messages=self._messages, tools=tools, model=self._gpt_model)
        return await self._handle_response(completion.choices[0], tools)

    async def _handle_tool_call(self, tool_call: ChatCompletionMessageToolCall):
        function_args = json.loads(tool_call.function.arguments)

        # TODO: actually use the tool
        self._messages.append({'tool_call_id': tool_call.id, 'role': 'tool', 'content': json.dumps(
            {'device': 'Kitchen Lights', 'attribute': 'state', 'value': 'ON'})})
