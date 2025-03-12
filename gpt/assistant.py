import asyncio as aio
from typing import List, Optional

from openai import AsyncOpenAI
from openai.types.beta import Assistant, Thread
from openai.types.beta.threads import RequiredActionFunctionToolCall

from gpt.functions import OpenAIFunction
from util import env_var, JSONObject


class PromptAssistant:
    """The assistant for the main prompt of the home."""

    def __init__(self, client: AsyncOpenAI, prompt: str, model: str = env_var('GPT_MODEL'),
                 tools: Optional[List[OpenAIFunction]] = None):
        super().__init__()

        self._client = client
        self._model = model
        self._tool_map = {f.get_name(): f for f in tools} if tools is not None else {}

        # Get the existing assistant or create a new one
        assistant_id = env_var('ASSISTANT_ID', True)
        self._assistant: Optional[Assistant] = None
        if assistant_id is not None:
            self._assistant = aio.run(self._client.beta.assistants.retrieve(assistant_id))
            # Update the model if necessary
            if self._assistant is not None:
                aio.run(self._client.beta.assistants.update(assistant_id=self._assistant.id,
                                                            model=self._model,
                                                            tools=[f.get_definition() for f in
                                                                   self._tool_map.values()]))
        if self._assistant is None:
            self._assistant = aio.run(self._client.beta.assistants.create(model=self._model,
                                                                          name='Home Assistant',
                                                                          instructions=prompt,
                                                                          tools=[f.get_definition() for f in
                                                                                 self._tool_map.values()]))
            print(f"Main home assistant created with id: '{self._assistant.id}'")
        if self._assistant is None:
            raise RuntimeError("Failed to instantiate assistant for main prompt")

        # Get the existing thread or create a new one
        thread_id = env_var('THREAD_ID', True)
        self._thread: Optional[Thread] = None
        if thread_id is not None:
            self._thread = aio.run(self._client.beta.threads.retrieve(thread_id))
        if self._thread is None:
            self._thread = aio.run(self._client.beta.threads.create())
            print(f"Main thread created with id: '{self._thread.id}'")
        if self._thread is None:
            raise RuntimeError("Failed to instantiate thread for main prompt")

    async def handle_user_message(self, message: str) -> str:
        """Process a single user message and return the result"""
        await self._client.beta.threads.messages.create(self._thread.id, role='user', content=message)

        run = await self._client.beta.threads.runs.create_and_poll(thread_id=self._thread.id,
                                                                   assistant_id=self._assistant.id)
        while run.status != 'completed':
            if run.status == 'requires_action':
                await self._handle_tool_calls(run.id, run.required_action.submit_tool_outputs.tool_calls)
                run = await self._client.beta.threads.runs.poll(run.id, self._thread.id)
        messages = await self._client.beta.threads.messages.list(self._thread.id)
        return messages.data[0].content[0].text.value

    async def _handle_tool_calls(self, run_id: str, calls: List[RequiredActionFunctionToolCall]):
        outputs = await aio.gather(*[self._handle_tool_call(call) for call in calls])
        await self._client.beta.threads.runs.submit_tool_outputs(run_id=run_id, thread_id=self._thread.id,
                                                                 tool_outputs=outputs)

    async def _handle_tool_call(self, call: RequiredActionFunctionToolCall) -> JSONObject:
        return {
            'tool_call_id': call.id,
            'output': await self._tool_map[call.function.name].invoke(call.function.arguments)
        }
