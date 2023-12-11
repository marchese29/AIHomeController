from dotenv import load_dotenv
from flask import Flask, jsonify, request

from gpt.client import OpenAISession
from gpt.functions import generate_device_query_tool
from gpt.prompt import generate_prompt
from hubitat.client import HubitatClient

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
    return jsonify(await openai_session.handle_user_message(request.form['message'],
                                                            tools=[generate_device_query_tool(['Kitchen Lights'])]))


if __name__ == '__main__':
    app.run(debug=True)
