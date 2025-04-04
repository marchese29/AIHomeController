"""Main application module for the AI Home Control system.

This module serves as the entry point for the AI Home Control application,
providing HTTP endpoints for user interaction and Hubitat device event handling.
"""

from dotenv import load_dotenv
from openai import AsyncOpenAI
from quart import Quart, jsonify, request

from gpt.assistant import AIHomeControlAssistant
from gpt.prompt import generate_prompt
from hubitat.client import HubitatClient
from hubitat.command import DeviceCommandFunction
from hubitat.query import DeviceQueryFunction, LayoutFunction
from hubitat.rules.manager import RuleManager, RuleProcessManager
from hubitat.rules.model import Rule
from hubitat.rules.tool import (
    DescribeRuleTool,
    ExecuteActionsTool,
    InstallRuleTool,
    ListAllRulesTool,
    UninstallRuleTool,
)
from hubitat.scenes.manager import SceneManager
from hubitat.scenes.tool import (
    CreateSceneTool,
    DeleteSceneTool,
    ListAllScenesTool,
)
from util import env_var

load_dotenv()

app = Quart(__name__)

he_client = HubitatClient()
he_client.load_devices()

rule_process = RuleProcessManager(he_client)
scene_manager = SceneManager(he_client, rule_process)
rule_manager = RuleManager(he_client, rule_process, scene_manager)

prompt = generate_prompt(he_client.devices)
print(prompt)
assistant = AIHomeControlAssistant(
    AsyncOpenAI(api_key=env_var("OPENAI_KEY")),
    prompt,
    tools=[
        DeviceCommandFunction(he_client),
        DeviceQueryFunction(he_client),
        LayoutFunction(he_client.devices),
        InstallRuleTool(rule_manager),
        DescribeRuleTool(rule_manager),
        ExecuteActionsTool(rule_manager),
        ListAllRulesTool(rule_manager),
        UninstallRuleTool(rule_manager),
        CreateSceneTool(scene_manager),
        DeleteSceneTool(scene_manager),
        ListAllScenesTool(scene_manager),
    ],
)


@app.post("/message")
async def user_prompt():
    """Handles a user prompt and returns a response from the assistant"""
    message = (await request.form)["message"]
    print(f'Message from the User: "{message}"')
    response = await assistant.handle_user_message(message)
    return jsonify(response)


@app.post("/he_event")
async def hubitat_device_event():
    """Endpoint that hubitat invokes when a device event occurs"""
    await he_client.handle_device_event((await request.json)["content"])
    return "Success"


@app.post("/install_rule")
async def install_rule():
    """Endpoint for manually installing a rule without the assistant"""
    rule = await request.json
    await rule_manager.install_rule(Rule.model_validate(rule))
    return "Success"


@app.before_serving
async def startup():
    """Initialize the application before serving requests"""
    await rule_manager.install_saved_rules()
    await scene_manager.install_saved_scenes()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
