import asyncio
import dataclasses
import importlib.util
import json
import logging
import os
import sys
import types
from pathlib import Path

import aiohttp


REPO_ROOT = Path(__file__).resolve().parent
GENERAC_DIR = REPO_ROOT / "custom_components" / "generac"
PACKAGE_NAME = "custom_components.generac"

custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [str(REPO_ROOT / "custom_components")]
generac_pkg = types.ModuleType(PACKAGE_NAME)
generac_pkg.__path__ = [str(GENERAC_DIR)]
sys.modules["custom_components"] = custom_components_pkg
sys.modules[PACKAGE_NAME] = generac_pkg

api_spec = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.api", GENERAC_DIR / "api.py"
)
api_module = importlib.util.module_from_spec(api_spec)
sys.modules[f"{PACKAGE_NAME}.api"] = api_module
api_spec.loader.exec_module(api_module)
GeneracApiClient = api_module.GeneracApiClient

logging.basicConfig(level=logging.DEBUG)


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


async def main():
    async with aiohttp.ClientSession() as session:
        api = GeneracApiClient(
            os.environ["GENERAC_USER"], os.environ["GENERAC_PASS"], session
        )
        await api.login()
        print(json.dumps(await api.get_generator_data(), cls=EnhancedJSONEncoder))


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
