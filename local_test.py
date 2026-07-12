"""Run a direct Auth0/DPoP API check from the repository."""
import asyncio
import dataclasses
import json
import os
import sys
import types
from pathlib import Path

import aiohttp


REPO_ROOT = Path(__file__).resolve().parent
GENERAC_DIR = REPO_ROOT / "custom_components" / "generac"
components = types.ModuleType("custom_components")
components.__path__ = [str(REPO_ROOT / "custom_components")]
package = types.ModuleType("custom_components.generac")
package.__path__ = [str(GENERAC_DIR)]
sys.modules["custom_components"] = components
sys.modules["custom_components.generac"] = package

from custom_components.generac.api import GeneracApiClient  # noqa: E402
from custom_components.generac.auth import GeneracAuth  # noqa: E402


class EnhancedJSONEncoder(json.JSONEncoder):
    """Serialize the dataclass API response for local inspection."""

    def default(self, value):
        if dataclasses.is_dataclass(value):
            return dataclasses.asdict(value)
        return super().default(value)


async def main() -> None:
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True, quote_cookie=False)
    ) as session:
        auth = await GeneracAuth.login(
            session, os.environ["GENERAC_USER"], os.environ["GENERAC_PASS"]
        )
        data = await GeneracApiClient(session, auth).async_get_data()
    print(json.dumps(data, cls=EnhancedJSONEncoder))


asyncio.run(main())
