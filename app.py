"""Main application module for the AI Home Control system.

This module serves as the entry point for the AI Home Control application,
providing HTTP endpoints for user interaction and Hubitat device event handling.
"""

import asyncio as aio
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from quart import Quart, jsonify, request

from gpt.assistant import AIHomeControlAssistant
from gpt.prompt import generate_prompt
from hubitat.rules.manager import RuleManager
from hubitat.rules.model import Rule
from hubitat.client import HubitatClient
from hubitat.command import DeviceCommandFunction
from hubitat.query import DeviceQueryFunction, LayoutFunction
from util import env_var
from utilities.time import CurrentTimeFunction

print("Starting application...")  # Debug print statement
load_dotenv()

app = Quart(__name__)

he_client = HubitatClient()
he_client.load_devices()

rule_manager = RuleManager(he_client)
RULE_PROCESS_LOCK: Optional[aio.Lock] = None

prompt = generate_prompt(he_client.devices)
print(prompt)
assistant = AIHomeControlAssistant(
    AsyncOpenAI(api_key=env_var('OPENAI_KEY')),
    prompt,
    tools=[
        DeviceCommandFunction(he_client),
        DeviceQueryFunction(he_client),
        LayoutFunction(he_client.devices),
        CurrentTimeFunction()
    ])


@app.post('/message')
async def user_prompt():
    """Handles a user prompt and returns a response from the assistant"""
    message = (await request.form)['message']
    print(f'Message from the User: "{message}"')
    response = await assistant.handle_user_message(message)
    return jsonify(response)


@app.post('/he_event')
async def hubitat_device_event():
    """Endpoint that hubitat invokes when a device event occurs"""
    async with RULE_PROCESS_LOCK:
        await he_client.handle_device_event((await request.json)['content'])
        return 'Success'


@app.post('/install_rule')
async def install_rule():
    """Endpoint for manually installing a rule without the assistant"""
    rule = await request.json
    async with RULE_PROCESS_LOCK:
        await rule_manager.install_rule(Rule.model_validate(rule))
    return 'Success'


@app.before_serving
async def startup():
    """Initialize application state before serving requests.

    This function is called by Quart before the application starts serving requests.
    It initializes the rule process lock to ensure thread-safe rule processing.
    """
    global RULE_PROCESS_LOCK
    RULE_PROCESS_LOCK = aio.Lock()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
