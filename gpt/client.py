import asyncio as aio
from copy import copy
from openai import OpenAI
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from typing import Any, Dict, List

from gpt.functions import OpenAIFunction
from hubitat.client import DeviceEvent
from util import env_var


class _MessageLog:
    """The central message log which can generate sessions for updating it"""

    def __init__(self):
        self._messages_lock = aio.Lock()
        self._messages: List[Dict[str, Any]] = []
        self._session_id: int = 0

    def unsafe_add_message(self, message: Dict[str, Any]):
        self._messages.append(message)

    async def get_messages(self) -> List[Dict[str, Any]]:
        async with self._messages_lock:
            return copy(self._messages)

    async def commit(self, new_messages: List[Dict[str, Any]]):
        async with self._messages_lock:
            self._messages.extend(new_messages)

    def session(self) -> '_MessageLogSession':
        return _MessageLogSession(self)


class _MessageLogSession:
    """Context managed session on the message log to avoid simultaneous updates on the log"""

    def __init__(self, message_log: _MessageLog):
        self._message_log = message_log

    async def __aenter__(self):
        self._old_messages = await self._message_log.get_messages()
        self._new_messages: List[Dict[str, Any]] = []
        return self

    def append(self, new_message: Dict[str, Any]):
        self._new_messages.append(new_message)

    def get_messages(self) -> List[Dict[str, Any]]:
        return self._old_messages + self._new_messages

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._message_log.commit(self._new_messages)


class OpenAISession:
    """Client wrapper for the OpenAI library"""

    def __init__(self):
        self._client = OpenAI(api_key=env_var('OPENAI_KEY'))
        self._gpt_model = env_var('GPT_MODEL')
        self._message_log = _MessageLog()
        self._functions: List[OpenAIFunction] = []
        self._function_map: Dict[str, OpenAIFunction] = {}

    def load_prompt(self, prompt: str):
        self._message_log.unsafe_add_message({'role': 'system', 'content': prompt})

    def load_functions(self, functions: List[OpenAIFunction]):
        self._functions = functions
        self._function_map = {f.get_name(): f for f in functions}

    async def handle_user_message(self, user_message: str) -> str:
        """Processes a message from the user, returns the response uttered by the LLM"""
        async with self._message_log.session() as session:
            session.append({'role': 'user', 'content': user_message})

            completion = self._run_completion(session)
            return await self._handle_response(completion.choices[0], session)

    async def handle_device_event(self, device_event: DeviceEvent):
        """Processes a device event"""
        async with self._message_log.session() as session:
            session.append({'role': 'user', 'content': f'Device Event: {device_event.model_dump_json()}'})

            completion = self._run_completion(session)
            print('GPT Device Event Response: ' + await self._handle_response(completion.choices[0], session))

    async def handle_timer_event(self, timer_name: str):
        """Processes a timer event"""
        async with self._message_log.session() as session:
            print(f'"{timer_name}" fired')
            session.append({'role': 'user', 'content': f'Timer Fired: {timer_name}'})

            completion = self._run_completion(session)
            print(f'GPT {timer_name} Timer Response: ' + await self._handle_response(completion.choices[0], session))

    async def _handle_response(self, choice: Choice, session: _MessageLogSession) -> str:
        match choice.finish_reason:
            case 'stop':
                session.append({'role': choice.message.role, 'content': choice.message.content})
                return choice.message.content
            case 'tool_calls':
                return await self._handle_tool_calls(choice, session)
            case _:
                raise Exception(f"Don't recognize the '{choice.finish_reason}' finish_reason")

    async def _handle_tool_calls(self, choice: Choice, session: _MessageLogSession) -> str:
        session.append({'role': choice.message.role, 'tool_calls': [
            {'id': tc.id, 'type': tc.type, 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}}
            for tc in choice.message.tool_calls]})

        tasks = []
        for tool_call in choice.message.tool_calls:
            tasks.append(aio.create_task(self._handle_tool_call(tool_call, session)))
        await aio.gather(*tasks)

        completion = self._run_completion(session)
        return await self._handle_response(completion.choices[0], session)

    async def _handle_tool_call(self, tool_call: ChatCompletionMessageToolCall, session: _MessageLogSession):
        function = self._function_map[tool_call.function.name]
        result = await function.invoke(tool_call.function.arguments)

        session.append({'tool_call_id': tool_call.id, 'role': 'tool', 'content': result})

    def _run_completion(self, session: _MessageLogSession) -> ChatCompletion:
        return self._client.chat.completions.create(messages=session.get_messages(),
                                                    tools=[f.get_definition() for f in self._functions],
                                                    model=self._gpt_model)
