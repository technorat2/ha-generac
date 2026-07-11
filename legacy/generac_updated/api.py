"""MobileLink API Client for Generac."""
import json
import logging
from typing import Any
from typing import Mapping
from urllib.parse import urljoin
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup
from dacite import from_dict

from .const import AUTH0_AUDIENCE
from .const import AUTH0_CLIENT_ID
from .const import AUTH0_PASSWORD_REALMS
from .const import AUTH0_SCOPE
from .const import AUTH0_SIGN_IN
from .const import AUTH0_TOKEN_URL
from .const import API_BASE
from .models import Apparatus
from .models import ApparatusDetail
from .models import Item


_LOGGER: logging.Logger = logging.getLogger(__package__)


class InvalidCredentialsException(Exception):
    pass


class SessionExpiredException(Exception):
    pass


class CannotConnectException(Exception):
    pass


class AuthFlowUnavailableException(Exception):
    pass


class GeneracApiClient:
    def __init__(
        self, username: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        """MobileLink API Client for Generac."""
        self._username = username
        self._password = password
        self._session = session
        self._logged_in = False
        self._auth_method = ""
        self.access_token = ""
        self.refresh_token = ""
        self.csrf = ""

    async def async_get_data(self) -> dict[str, Item] | None:
        """Get data from the API."""
        try:
            if not self._logged_in:
                await self.login()
                self._logged_in = True
            return await self.get_generator_data()
        except SessionExpiredException:
            self._logged_in = False
            if self.refresh_token and await self.refresh_tokens():
                self._logged_in = True
                return await self.get_generator_data()

            await self.login()
            self._logged_in = True
            return await self.get_generator_data()

    async def get_generator_data(self):
        apparatuses = await self.get_endpoint("/v2/Apparatus/list")
        if apparatuses is None:
            _LOGGER.debug("Could not decode apparatuses response")
            return None
        if not isinstance(apparatuses, list):
            _LOGGER.error("Expected list from /v2/Apparatus/list got %s", apparatuses)

        data: dict[str, Item] = {}
        for apparatus in apparatuses:
            apparatus = from_dict(Apparatus, apparatus)
            if apparatus.type != 0:
                _LOGGER.debug(
                    "Unknown apparatus type %s %s", apparatus.type, apparatus.name
                )
                continue
            detail_json = await self.get_endpoint(
                f"/v1/Apparatus/details/{apparatus.apparatusId}"
            )
            if detail_json is None:
                _LOGGER.debug(
                    f"Could not decode respose from /v1/Apparatus/details/{apparatus.apparatusId}"
                )
                continue
            detail = from_dict(ApparatusDetail, detail_json)
            data[str(apparatus.apparatusId)] = Item(apparatus, detail)
        return data

    async def get_endpoint(self, endpoint: str):
        try:
            response = await self._session.get(API_BASE + endpoint, headers=self.headers)
            if response.status == 204:
                # no data
                return None

            if response.status in (401, 403):
                raise SessionExpiredException(
                    "API session expired: %s" % response.status
                )

            if response.status != 200:
                raise SessionExpiredException(
                    "API returned status code: %s " % response.status
                )

            data = await response.json()
            _LOGGER.debug("getEndpoint %s", json.dumps(data))
            return data
        except SessionExpiredException:
            raise
        except Exception as ex:
            raise CannotConnectException() from ex

    @property
    def headers(self) -> dict[str, str]:
        """Return auth headers for whichever login method is active."""
        headers = {}
        if self.csrf:
            headers["X-Csrf-Token"] = self.csrf
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def login(self) -> None:
        """Login to the Mobile Link API.

        The current mobile APK uses Auth0 native login with bearer tokens. Auth0
        does not currently allow a direct password grant for this public client,
        so the integration first tries the token path and then falls back to the
        Mobile Link web sign-in flow that sets the same API cookies used by the
        website.
        """
        self._auth_method = ""
        self.access_token = ""
        self.refresh_token = ""
        self.csrf = ""

        try:
            await self.login_with_auth0_tokens()
            return
        except AuthFlowUnavailableException as err:
            _LOGGER.debug("Auth0 token login is not available: %s", err)
        except InvalidCredentialsException:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.debug("Auth0 token login connection failed: %s", err)
        except Exception:
            _LOGGER.exception("Unexpected error during Auth0 token login")

        await self.login_with_mobile_link_web()

    async def login_with_auth0_tokens(self) -> None:
        """Try the Auth0 token grants exposed by the mobile APK."""
        password_grants: list[dict[str, str]] = [
            {
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
                "client_id": AUTH0_CLIENT_ID,
                "audience": AUTH0_AUDIENCE,
                "scope": AUTH0_SCOPE,
            }
        ]
        password_grants.extend(
            {
                "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
                "username": self._username,
                "password": self._password,
                "realm": realm,
                "client_id": AUTH0_CLIENT_ID,
                "audience": AUTH0_AUDIENCE,
                "scope": AUTH0_SCOPE,
            }
            for realm in AUTH0_PASSWORD_REALMS
        )

        last_error = ""
        for payload in password_grants:
            token_response = await self._session.post(
                AUTH0_TOKEN_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            token_data = await self._safe_json(token_response)
            if token_response.status == 200:
                self._set_tokens(token_data)
                self._auth_method = "auth0_token"
                return

            error_code = token_data.get("error", "")
            error_description = token_data.get("error_description", "")
            last_error = error_description or error_code or str(token_response.status)
            _LOGGER.debug(
                "Auth0 token grant %s failed with %s: %s",
                payload["grant_type"],
                token_response.status,
                last_error,
            )

            if token_response.status in (401, 403) and error_code not in (
                "unauthorized_client",
                "invalid_grant",
            ):
                raise InvalidCredentialsException()

        raise AuthFlowUnavailableException(last_error or "password grant unavailable")

    async def refresh_tokens(self) -> bool:
        """Refresh Auth0 tokens when token auth is active."""
        if not self.refresh_token:
            return False

        token_response = await self._session.post(
            AUTH0_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "client_id": AUTH0_CLIENT_ID,
                "refresh_token": self.refresh_token,
            },
            headers={"Content-Type": "application/json"},
        )
        if token_response.status != 200:
            _LOGGER.debug("Auth0 refresh token failed with %s", token_response.status)
            self.access_token = ""
            self.refresh_token = ""
            return False

        self._set_tokens(await self._safe_json(token_response))
        self._auth_method = "auth0_token"
        return True

    def _set_tokens(self, token_data: Mapping[str, Any]) -> None:
        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthFlowUnavailableException("Auth0 response did not include token")

        self.access_token = str(access_token)
        refresh_token = token_data.get("refresh_token")
        if refresh_token:
            self.refresh_token = str(refresh_token)

    async def login_with_mobile_link_web(self) -> None:
        """Login through Mobile Link's Auth0 web bridge and keep API cookies."""
        try:
            response = await self._session.get(
                f"{AUTH0_SIGN_IN}?{urlencode({'userEmail': self._username})}",
                allow_redirects=True,
            )
        except aiohttp.ClientError as err:
            raise CannotConnectException("Unable to open Mobile Link login") from err

        for _ in range(4):
            if self._is_mobile_link_app_url(str(response.url)):
                self._auth_method = "mobile_link_cookie"
                return

            page = await response.text()
            if self._page_has_auth_error(page):
                raise InvalidCredentialsException()

            form = BeautifulSoup(page, features="html.parser").select_one("form")
            if form is None:
                _LOGGER.debug("Could not find Auth0 login form at %s", response.url)
                raise CannotConnectException("Unable to find Auth0 login form")

            response = await self.submit_form(
                response,
                form,
                {
                    "email": self._username,
                    "username": self._username,
                    "password": self._password,
                },
            )

        raise CannotConnectException("Auth0 login did not complete")

    @staticmethod
    async def _safe_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            data = await response.json(content_type=None)
        except Exception:  # pylint: disable=broad-except
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_mobile_link_app_url(url: str) -> bool:
        return url.startswith("https://app.mobilelinkgen.com/")

    @staticmethod
    def _page_has_auth_error(page: str) -> bool:
        lowered = page.lower()
        return any(
            message in lowered
            for message in (
                "wrong email or password",
                "incorrect email or password",
                "invalid email or password",
                "invalid username or password",
            )
        )

    async def submit_form(
        self,
        response: aiohttp.ClientResponse,
        form: Any,
        overrides: Mapping[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        """Submit an HTML form while preserving hidden Auth0 fields."""
        if form is None:
            raise CannotConnectException("Could not find login form")

        action = form.attrs.get("action")
        if action is None:
            action = str(response.url)

        form_data = []
        fields = set()
        overrides = overrides or {}
        for input_element in form.select("input[name]"):
            name = input_element.attrs["name"]
            fields.add(name)
            form_data.append((name, self._form_value(name, input_element, overrides)))

        login_response = await self._session.post(
            urljoin(str(response.url), action),
            data=form_data,
            allow_redirects=True,
        )

        if login_response.status >= 400:
            page = await login_response.text()
            if self._page_has_auth_error(page):
                raise InvalidCredentialsException()
            raise CannotConnectException(
                f"Bad api login response: {login_response.status}"
            )
        return login_response

    @staticmethod
    def _form_value(
        name: str, input_element: Any, overrides: Mapping[str, str]
    ) -> str:
        field_type = input_element.attrs.get("type", "").lower()
        lower_name = name.lower()
        if name in overrides:
            return overrides[name]
        if field_type == "password" or "password" in lower_name:
            return overrides.get("password", "")
        if lower_name in ("email", "username", "login", "signinname"):
            return overrides.get("username", overrides.get("email", ""))
        return input_element.attrs.get("value", "")
