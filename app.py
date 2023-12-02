from dotenv import load_dotenv
from flask import Flask, jsonify

from gpt.client import OpenAISession
from gpt.functions import generate_device_query_tool
from gpt.prompt import generate_prompt

load_dotenv()

app = Flask(__name__)

openai_session = OpenAISession(prompt=generate_prompt())


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.get('/prompt')
async def user_prompt():
    return jsonify(openai_session.handle_user_message('Are the kitchen lights on?',
                                                      tools=[generate_device_query_tool(['Kitchen Lights'])]))


if __name__ == '__main__':
    app.run(debug=True)