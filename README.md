# AIHomeController

Have you ever wondered what it would be like to control your home using conversational english?  This is your chance!

I have connected the OpenAI API's with Hubitat so that ChatGPT can control your devices and answer questions about your
home.

## Possibilities

* Control any devices in your home which you have exposed through the Hubitat Maker API
  * "It's getting a little dark, could you turn on the lights in the Kitchen?  But please don't blind me, 25% brightness should be plenty."
  * AIHC: "Of course, I've turned on the lights in the Kitchen to 25%"
* Ask about the devices in your house
  * "It's starting to get a little warm in the living room, what's the current temperature reading in there?"
  * AIHC: "It's currently 72 degrees in the living room"
  * "Yeah that's too hot, if the thermostat is set above 70 could you turn it down a couple degrees?"
  * AIHC: "Certainly, the thermostat was set to 71 degrees, I've turned it down to 69 degrees"
* React to device state changes
  * "I'm expecting some guests, if you sense any movement in the foyer, could you turn on the lights for whoever has entered?"
  * AIHC: "Sure, I will turn on the lights in the Foyer if I detect any movement there"
* Remember your preferences
  * "Hey, whenever I tell you to turn out all the lights, you should still leave the nightlight on in the bedroom"
  * AIHC: "Okay, I will be sure to leave the nightlight on when you turn off all the lights in the future"
* Time based commands:
  * "I'll be getting home from work late tomorrow, can you turn the outside lights on at 6pm?"
  * AIHC: "I will be sure to turn on the Outside Lights at 6pm tomorrow"

## Future Features

* Support for more hubitat capabilities (thermostats, door locks, etc.)
* Support for local information like weather and sunset/sunrise time
* A template for more arbitrary integrations
* Automatic configuration of HE Maker API's POST event setup
* Probably some model fine-tuning, this thing is really bad at knowing what is in each room and time things

# SETUP

The system is pretty useless in the free tier of OpenAI's API's - you will want to kick over $5 so that you don't get
throttled at 3 requests per minute.  You will also need to set up an instance of the Hubitat Maker API and get the HE's
address, app_id, and access_token.  The parameters are stored in a ".env" file:

```
OPENAI_KEY=sk-ABCDEFG
GPT_MODEL=gpt-3.5-turbo-1106  # I tested with this one, feel free to try others
HE_ADDRESS=XXX.XX.XX.XXX
HE_APP_ID=XXX
HE_ACCESS_TOKEN=dead-beef-01ce-c01d

HOME_LOCATION='Seattle, Washington'
HOME_LAYOUT='* The Foyer and Garage are on the ground floor
* The Dining Room, Kitchen, and Living Room are on the second floor
* There is a flight of stairs from the Foyer to the Dining Room
* The Bedroom, Office, Bunny Room, and Hallway are on the third floor
* The Hallway connects all other rooms on the third floor
* There is a flight of stairs from the Living Room to the Hallway
* The Patio is on the roof of the house (the fourth floor), it is outside
* There is a flight of stairs from the Hallway to the Patio'
```

### Install Dependencies

Python 3.12 or newer is required

```
> pip install -r requirements.txt
```

### Run the server

```
> python -m flask run -h 0.0.0.0 -p 8080
```

Take note of the "running on" address that isn't `127.0.0.1`

### Set up the Hubitat Post Events

In the maker API configuration page on hubitat, set up the POST event endpoint: `http://<ip_addr>:8080/he_event`

### Make Requests

Messages are sent to the server by posting with a "message" attribute on the "/message" endpoint