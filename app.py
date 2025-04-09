"""Main application module for the AI Home Control system.

This module serves as the entry point for the AI Home Control application,
providing HTTP endpoints for user interaction and Hubitat device event handling.
"""

from dotenv import load_dotenv
from openai import AsyncOpenAI
from quart import Quart, jsonify, request

from gpt.controller import AIHomeController
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
from utilities.clock import ClockService
from utilities.timers import TimerService

load_dotenv()

app = Quart(__name__)


@app.post("/message")
async def user_prompt():
    """Handles a user prompt and returns a response from the assistant"""
    message = (await request.form)["message"]
    print(f'Message from the User: "{message}"')
    response = await app.controller.handle_user_message(message)
    return jsonify(response)


@app.post("/he_event")
async def hubitat_device_event():
    """Endpoint that hubitat invokes when a device event occurs"""
    await app.he_client.handle_device_event((await request.json)["content"])
    return "Success"


@app.post("/install_rule")
async def install_rule():
    """Endpoint for manually installing a rule without the assistant"""
    rule = await request.json
    await app.rule_manager.install_rule(Rule.model_validate(rule))
    return "Success"


@app.before_serving
async def startup():
    """Initialize the application before serving requests"""

    # Initialize the Hubitat client
    app.he_client = HubitatClient()
    app.he_client.load_devices()

    # Initialize services
    app.timer_service = TimerService()
    app.timer_service.start()
    app.clock_service = ClockService()
    app.clock_service.start()
    app.rule_process = RuleProcessManager(
        app.he_client, app.timer_service, app.clock_service
    )

    # Initialize managers
    app.scene_manager = SceneManager(app.he_client, app.rule_process)
    app.rule_manager = RuleManager(app.he_client, app.rule_process, app.scene_manager)

    await app.rule_manager.install_saved_rules()
    await app.scene_manager.install_saved_scenes()

    # Initialize OpenAI client
    ai_client = AsyncOpenAI(api_key=env_var("OPENAI_KEY"))

    # Define common tools needed by all assistants
    common_tools = [
        DeviceCommandFunction(app.he_client),
        DeviceQueryFunction(app.he_client),
        LayoutFunction(app.he_client.devices),
        ListAllRulesTool(app.rule_manager),
        ListAllScenesTool(app.scene_manager),
    ]

    # Tools specific to the main assistant
    main_tools = [*common_tools]

    # Tools specific to the rules assistant
    rules_tools = [
        *common_tools,
        InstallRuleTool(app.rule_manager),
        UninstallRuleTool(app.rule_manager),
        DescribeRuleTool(app.rule_manager),
        ExecuteActionsTool(app.rule_manager),
    ]

    # Tools specific to the scenes assistant
    scenes_tools = [
        *common_tools,
        CreateSceneTool(app.scene_manager),
        DeleteSceneTool(app.scene_manager),
    ]

    # Initialize the controller with all assistant types
    app.controller = AIHomeController(
        ai_client,
        app.he_client,
        main_tools,
        rules_tools,
        scenes_tools,
    )
    await app.controller.initialize()


@app.after_serving
async def shutdown():
    """Shutdown the application"""
    await app.timer_service.stop()
    await app.clock_service.stop()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
