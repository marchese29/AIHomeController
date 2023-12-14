from dotenv import load_dotenv
from flask import Flask, jsonify, request

from gpt.client import OpenAISession
from gpt.prompt import generate_prompt
from hubitat.client import HubitatClient
from hubitat.command import DeviceCommandFunction
from hubitat.query import DeviceQueryFunction

load_dotenv()

app = Flask(__name__)

he_client = HubitatClient()
openai_session = OpenAISession(functions=[DeviceCommandFunction(he_client), DeviceQueryFunction(he_client)])

he_client.load_devices()
openai_session.load_prompt(generate_prompt(he_client.devices))


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.post('/message')
async def user_prompt():
    response = await openai_session.handle_user_message(request.form['message'])
    return jsonify(response)


if __name__ == '__main__':
    app.run(debug=True)
