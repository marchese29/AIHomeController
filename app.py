from dotenv import load_dotenv
from flask import Flask, jsonify
import json
from openai import AsyncOpenAI
import os
import sys
from typing import Optional

from gpt.functions import generate_device_query_tool
from gpt.prompt import generate_prompt


def env_var(name: str, allow_null: bool = False) -> Optional[str]:
    """A useful utility for validating the presence of an environment variable before loading"""
    if not allow_null and name not in os.environ:
        sys.exit(f'{name} was not set in the environment')
    value = os.environ[name]
    if not allow_null and value is None:
        sys.exit(f'The value of {name} in the environment cannot be empty')
    return value


load_dotenv()
OPENAI_KEY = env_var('OPENAI_KEY')
GPT_MODEL = env_var('GPT_MODEL')

app = Flask(__name__)


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.get('/prompt')
async def user_prompt():
    ai_client = AsyncOpenAI(api_key=OPENAI_KEY)

    messages = [{'role': 'system', 'content': generate_prompt()},
                {'role': 'user', 'content': 'Are the kitchen lights on?'}]

    completion = await ai_client.chat.completions.create(messages=messages,
                                                         tools=[generate_device_query_tool(['Kitchen Lights'])],
                                                         model=GPT_MODEL)

    choice = completion.choices[0]
    if choice.finish_reason == 'tool_calls':
        tool_call = choice.message.tool_calls[0]
        messages.append({
            'role': 'assistant',
            'tool_calls': [{'id': tool_call.id, 'type': 'function',
                            'function': {'name': tool_call.function.name, 'arguments': tool_call.function.arguments}}]
        })

        function_args = json.loads(tool_call.function.arguments)
        messages.append({'tool_call_id': tool_call.id, 'role': 'tool', 'content': json.dumps(
            {'device': function_args['queries'][0]['device'],
             'attribute': function_args['queries'][0]['attribute'],
             'value': 'ON'})})

        function_completion = await ai_client.chat.completions.create(messages=messages,
                                                                      tools=[generate_device_query_tool(
                                                                          ['Kitchen Lights'])],
                                                                      model=GPT_MODEL)
        if function_completion.choices[0].finish_reason == 'stop':
            return function_completion.choices[0].message.content
        return jsonify(function_args)

    return jsonify(completion)


if __name__ == '__main__':
    app.run(debug=True)
