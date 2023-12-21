from dotenv import load_dotenv
from flask import Flask, jsonify, request

from gpt.client import OpenAISession
from gpt.prompt import generate_prompt
from hubitat.client import HubitatClient
from hubitat.command import DeviceCommandFunction
from hubitat.query import DeviceQueryFunction, LayoutFunction
from hubitat.subscribe import SubscribeFunction, UnsubscribeFunction
from utilities.time import CurrentTimeFunction, TimeDifferenceFunction, TimerFunction

load_dotenv()

app = Flask(__name__)

he_client = HubitatClient()
openai_session = OpenAISession()

he_client.load_devices()
openai_session.load_prompt(generate_prompt(he_client.devices))
openai_session.load_functions(
    [DeviceCommandFunction(he_client),
     DeviceQueryFunction(he_client),
     SubscribeFunction(he_client, openai_session),
     UnsubscribeFunction(he_client),
     LayoutFunction(he_client.devices),
     TimerFunction(openai_session),
     TimeDifferenceFunction(),
     CurrentTimeFunction()])


@app.post('/message')
async def user_prompt():
    message = request.form['message']
    print(f'Message from the User: "{message}"')
    response = await openai_session.handle_user_message(message)
    return jsonify(response)


@app.post('/he_event')
async def hubitat_device_event():
    await he_client.handle_device_event(request.json['content'])
    return 'Success'


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
