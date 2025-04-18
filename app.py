"""Main application module for the AI Home Control system.

This module serves as the entry point for the AI Home Control application,
providing HTTP endpoints for user interaction and Hubitat device event handling.
"""

from dotenv import load_dotenv
from openai import AsyncOpenAI
from quart import Quart, jsonify, request

from gpt.controller import AIHomeController
from hubitat.client import HubitatClient
from util import env_var

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


# @app.post("/install_rule")
# async def install_rule():
#     """Endpoint for manually installing a rule without the assistant"""
#     rule = await request.json
#     await app.rule_manager.install_rule(Rule.model_validate(rule))
#     return "Success"


@app.before_serving
async def startup():
    """Initialize the application before serving requests"""

    # Initialize the Hubitat client
    app.he_client = HubitatClient()
    app.he_client.load_devices()

    await app.rule_manager.install_saved_rules()
    await app.scene_manager.install_saved_scenes()

    # Initialize OpenAI client
    ai_client = AsyncOpenAI(api_key=env_var("OPENAI_KEY"))
    app.controller = AIHomeController(ai_client)

    # Define common tools needed by all assistants
    await app.controller.initialize()


@app.after_serving
async def shutdown():
    """Shutdown the application"""
    await app.timer_service.stop()
    await app.clock_service.stop()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
