import asyncio as aio
from enum import Enum
from typing import Literal, Optional

from openai import AsyncOpenAI
from openai.types.beta import Assistant, Thread
from openai.types.beta.threads import RequiredActionFunctionToolCall
from pydantic import BaseModel, Field

from gpt.functions import OpenAIFunction
from gpt.prompt import generate_prompt
from hubitat.client import HubitatClient
from util import JSONObject, env_var


class AssistantType(Enum):
    """Enum representing the different types of assistants."""

    MAIN = ("main", "Home Assistant", "GPT_MODEL", "ASSISTANT_ID", "THREAD_ID")
    RULES = (
        "rules",
        "Rules Assistant",
        "RULES_GPT_MODEL",
        "RULES_ASSISTANT_ID",
        "RULES_THREAD_ID",
    )
    SCENES = (
        "scenes",
        "Scenes Assistant",
        "SCENES_GPT_MODEL",
        "SCENES_ASSISTANT_ID",
        "SCENES_THREAD_ID",
    )

    @property
    def assistant_type(self) -> str:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @property
    def model_var_name(self) -> str:
        return self.value[2]

    @property
    def assistant_id_var_name(self) -> str:
        return self.value[3]

    @property
    def thread_id_var_name(self) -> str:
        return self.value[4]

    @classmethod
    def from_type_name(cls, type_name: str) -> "AssistantType":
        """Get the enum by the first value in its tuple.

        Args:
            type_name: The type name to look up.

        Returns:
            The matching AssistantType enum value.

        Raises:
            ValueError: If no enum value matches the type string.
        """
        for enum_value in cls:
            if enum_value.value[0] == type_name:
                return enum_value
        raise ValueError(f"No AssistantType found for type: {type_name}")


async def _get_or_create_assistant(
    client: AsyncOpenAI,
    prompt: str,
    tools: list[OpenAIFunction],
    assistant_type: AssistantType,
) -> Assistant:
    """Get an existing assistant or create a new one.

    Args:
        client: The OpenAI client.
        prompt: The instructions for the assistant.
        tools: The tools the assistant can use.
        assistant_type: The type of assistant to get or create.

    Returns:
        The retrieved or created assistant.
    """
    assistant_id = env_var(assistant_type.assistant_id_var_name, True)
    assistant_id = None if assistant_id is None or assistant_id == "" else assistant_id
    assistant: Optional[Assistant] = None

    if assistant_id is not None:
        assistant = await client.beta.assistants.retrieve(assistant_id)
        # Update the assistant if necessary
        if assistant is not None:
            assistant = await client.beta.assistants.update(
                assistant_id=assistant.id,
                model=env_var(assistant_type.model_var_name),
                instructions=prompt,
                tools=[f.get_definition() for f in tools],
            )

    if assistant is None:
        assistant = await client.beta.assistants.create(
            model=env_var(assistant_type.model_var_name),
            name=assistant_type.name,
            instructions=prompt,
            tools=[f.get_definition() for f in tools],
        )
        print(f"{assistant_type.name} created with id: '{assistant.id}'")

    if assistant is None:
        raise RuntimeError("Failed to instantiate assistant for main prompt")

    return assistant


async def _get_or_create_thread(
    client: AsyncOpenAI,
    assistant_type: AssistantType,
) -> Thread:
    """Get an existing thread or create a new one.

    Args:
        client: The OpenAI client.
        assistant_type: The type of assistant to get or create a thread for.

    Returns:
        The retrieved or created thread.
    """
    thread_id = env_var(assistant_type.thread_id_var_name, True)
    thread_id = None if thread_id is None or thread_id == "" else thread_id
    thread: Optional[Thread] = None

    if thread_id is not None:
        thread = await client.beta.threads.retrieve(thread_id)

    if thread is None:
        thread = await client.beta.threads.create()
        print(f"{assistant_type.name} thread created with id: '{thread.id}'")

    if thread is None:
        raise RuntimeError("Failed to instantiate thread for main prompt")

    return thread


class ResponseModel(BaseModel):
    """A unified response model for all assistant interactions."""

    mode: Literal["MAIN", "RULES", "SCENES"] = Field(
        description="The mode that should handle this response"
    )
    message: Optional[str] = Field(
        description=(
            "The message to read out loud to the user. "
            "If mode is changing, leave null to allow new mode to respond."
        ),
        default=None,
    )
    context: Optional[str] = Field(
        description=(
            "Context for the new mode. "
            "REQUIRED if mode is changing, ignored if mode is not changing."
        ),
        default=None,
    )


class StateError(Exception):
    """Exception raised for state-related errors in the controller."""

    pass


class AIHomeController:
    """Controller for managing multiple AI assistants specialized for different home
    automation tasks.

    This class manages three different types of assistants:
    - MAIN: The primary assistant for general home control and user interaction
    - RULES: A specialist for creating and managing automation rules
    - SCENES: A specialist for creating and managing scenes/routines

    The controller handles routing messages to the appropriate assistant and managing mode
    changes between specialists. Each assistant has its own persistent thread for
    maintaining conversation context.
    """

    def __init__(
        self,
        ai_client: AsyncOpenAI,
        he_client: HubitatClient,
        main_tools: list[OpenAIFunction],
        rules_tools: list[OpenAIFunction],
        scenes_tools: list[OpenAIFunction],
    ):
        self._client = ai_client
        self._current_mode = AssistantType.MAIN

        # Create tool maps for each assistant type
        self._tool_maps = {
            AssistantType.MAIN: {f.get_name(): f for f in main_tools},
            AssistantType.RULES: {f.get_name(): f for f in rules_tools},
            AssistantType.SCENES: {f.get_name(): f for f in scenes_tools},
        }

        self._assistants = {
            AssistantType.MAIN: aio.run(
                _get_or_create_assistant(
                    self._client,
                    generate_prompt(
                        he_client.devices, AssistantType.MAIN.assistant_type
                    ),
                    main_tools,
                    AssistantType.MAIN,
                )
            ),
            AssistantType.RULES: aio.run(
                _get_or_create_assistant(
                    self._client,
                    generate_prompt(
                        he_client.devices, AssistantType.RULES.assistant_type
                    ),
                    rules_tools,
                    AssistantType.RULES,
                )
            ),
            AssistantType.SCENES: aio.run(
                _get_or_create_assistant(
                    self._client,
                    generate_prompt(
                        he_client.devices, AssistantType.SCENES.assistant_type
                    ),
                    scenes_tools,
                    AssistantType.SCENES,
                )
            ),
        }
        self._threads = {
            AssistantType.MAIN: aio.run(
                _get_or_create_thread(self._client, AssistantType.MAIN)
            ),
            AssistantType.RULES: aio.run(
                _get_or_create_thread(self._client, AssistantType.RULES)
            ),
            AssistantType.SCENES: aio.run(
                _get_or_create_thread(self._client, AssistantType.SCENES)
            ),
        }

    async def handle_user_message(self, message: str) -> str:
        """Process a user message and route it to the appropriate assistant.

        Args:
            message: The message from the user.

        Returns:
            A response message to be read to the user.

        Raises:
            StateError: If a mode change is requested without providing context,
                       or if mode isn't changing but no message is provided.
        """
        # Get the current assistant and thread
        assistant = self._assistants[self._current_mode]
        thread = self._threads[self._current_mode]

        # Send message to thread
        await self._client.beta.threads.messages.create(
            thread.id, role="user", content=message
        )

        # Run the assistant
        run = await self._client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id,
            response_format=ResponseModel,
        )

        # Handle tool calls if needed
        while run.status != "completed":
            if run.status == "requires_action":
                await self._handle_tool_calls(
                    run.id, run.required_action.submit_tool_outputs.tool_calls
                )
                run = await self._client.beta.threads.runs.poll(run.id, thread.id)

        # Get the response
        messages = await self._client.beta.threads.messages.list(thread.id)
        response = messages.data[0].content[0].response.parsed

        # Check if mode change is needed
        requested_mode = AssistantType.from_type_name(response.mode)
        if requested_mode != self._current_mode:
            # Mode change needed - context MUST be provided
            if not response.context:
                raise StateError(
                    f"Mode change from {self._current_mode.name} to "
                    f"{requested_mode.name} requested without providing context"
                )

            # Update the current mode
            self._current_mode = requested_mode

            # If a message is provided, return it directly
            if response.message is not None:
                return response.message

            # Otherwise, forward context to the new assistant
            return await self.handle_user_message(response.context)
        else:
            # Same mode - message MUST be provided
            if not response.message:
                raise StateError(
                    f"No message provided when staying in mode {self._current_mode.name}"
                )

            # Return the response message
            return response.message

    async def _handle_tool_calls(
        self, run_id: str, calls: list[RequiredActionFunctionToolCall]
    ):
        """Process a list of tool calls and submit the outputs.

        Args:
            run_id: The ID of the current run.
            calls: The list of tool calls to process.
        """
        tool_map = self._tool_maps[self._current_mode]
        outputs = await aio.gather(
            *[self._handle_tool_call(call, tool_map) for call in calls]
        )
        await self._client.beta.threads.runs.submit_tool_outputs(
            run_id=run_id,
            thread_id=self._threads[self._current_mode].id,
            tool_outputs=outputs,
        )

    async def _handle_tool_call(
        self, call: RequiredActionFunctionToolCall, tool_map: dict[str, OpenAIFunction]
    ) -> JSONObject:
        """Process a single tool call.

        Args:
            call: The tool call to process.
            tool_map: The map of tool names to tool functions.

        Returns:
            A JSON object containing the tool call ID and output.
        """
        if call.function.name not in tool_map:
            return {
                "tool_call_id": call.id,
                "output": f"Tool '{call.function.name}' not found",
            }
        return {
            "tool_call_id": call.id,
            "output": await tool_map[call.function.name].invoke(
                call.function.arguments
            ),
        }
