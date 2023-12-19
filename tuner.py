"""Generates a tuning dataset for the configuration of the hubitat."""
import asyncio
from dotenv import load_dotenv
import sys

from hubitat.client import HubitatClient

load_dotenv()


async def main() -> str | int:
    """The main entry point for the program"""

    # First, set up the hubitat client and load the devices for this home
    he_client = HubitatClient()
    he_client.load_devices()

    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
