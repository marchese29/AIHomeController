from dotenv import load_dotenv
from flask import Flask, jsonify, request

from gpt.client import OpenAISession
from gpt.functions import generate_command_tool, generate_device_query_tool
from gpt.prompt import generate_prompt
from hubitat.client import HubitatClient, capability_commands

load_dotenv()

app = Flask(__name__)

openai_session = OpenAISession()
he_client = HubitatClient()

he_client.load_devices()
openai_session.load_prompt(generate_prompt(he_client.devices))


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.post('/message')
async def user_prompt():
    tools = [generate_device_query_tool(he_client.devices), generate_command_tool(capability_commands)]
    response = await openai_session.handle_user_message(request.form['message'], tools=tools)
    return jsonify(response)


if __name__ == '__main__':
    app.run(debug=True)
