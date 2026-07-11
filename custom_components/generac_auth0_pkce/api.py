"""MobileLink API Client for Generac."""
import asyncio
import base64
import binascii
import hashlib
import json
import logging
import secrets
import time
from typing import Any
from typing import Callable
from typing import Mapping
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from dacite import from_dict

from .const import AUTH0_AUDIENCE
from .const import AUTH0_AUTHORIZE_URL
from .const import AUTH0_CLIENT_HEADER
from .const import AUTH0_CLIENT_ID
from .const import AUTH0_REDIRECT_URI
from .const import AUTH0_SCOPE
from .const import AUTH0_SIGN_IN
from .const import AUTH0_TOKEN_URL
from .const import AUTH_MODE_PKCE
from .const import AUTH_MODE_WEB_COOKIE
from .const import API_BASE
from .const import API_V5_BASE
from .const import CONF_AUTH_MODE
from .const import MOBILE_API_USER_AGENT
from .models import Apparatus
from .models import ApparatusDetail
from .models import Item


_LOGGER: logging.Logger = logging.getLogger(__package__)
TOKEN_EXPIRY_SKEW = 60


class InvalidCredentialsException(Exception):
    """Raised when Generac or Auth0 rejects the supplied credentials."""


class SessionExpiredException(Exception):
    """Raised when an authenticated Mobile Link request is rejected."""


class CannotConnectException(Exception):
    """Raised when Mobile Link cannot be reached or returns invalid data."""


class AuthFlowUnavailableException(Exception):
    """Raised when an authentication response cannot be used."""


class Auth0PkceSession:
    """Utilities for Auth0 authorization-code PKCE login."""

    @staticmethod
    def create() -> dict[str, str]:
        """Create PKCE state and the Auth0 hosted-login URL."""
        code_verifier = Auth0PkceSession._token_urlsafe(96)
        state = Auth0PkceSession._token_urlsafe(32)
        nonce = Auth0PkceSession._token_urlsafe(32)
        code_challenge = Auth0PkceSession._code_challenge(code_verifier)
        query = {
            "client_id": AUTH0_CLIENT_ID,
            "redirect_uri": AUTH0_REDIRECT_URI,
            "response_type": "code",
            "scope": AUTH0_SCOPE,
            "audience": AUTH0_AUDIENCE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "login",
        }
        return {
            "auth_url": f"{AUTH0_AUTHORIZE_URL}?{urlencode(query)}",
            "code_verifier": code_verifier,
            "state": state,
            "nonce": nonce,
        }

    @staticmethod
    async def exchange_callback(
        session: aiohttp.ClientSession,
        callback_url: str,
        code_verifier: str,
        expected_state: str,
    ) -> dict[str, Any]:
        """Exchange a pasted Auth0 callback URL for OAuth tokens."""
        parsed = urlparse(callback_url)
        query = parse_qs(parsed.query)
        error = Auth0PkceSession._first(query, "error")
        if error:
            description = Auth0PkceSession._first(query, "error_description")
            raise InvalidCredentialsException(description or error)

        state = Auth0PkceSession._first(query, "state")
        if state != expected_state:
            raise CannotConnectException("Auth0 state did not match this login attempt")

        code = Auth0PkceSession._first(query, "code")
        if not code:
            raise CannotConnectException("Auth0 callback did not include a code")

        try:
            async with session.post(
                AUTH0_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": AUTH0_CLIENT_ID,
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": AUTH0_REDIRECT_URI,
                },
                headers=Auth0PkceSession.auth0_headers(),
            ) as token_response:
                token_data = await GeneracApiClient.safe_json(token_response)
                if token_response.status != 200:
                    error_description = token_data.get("error_description")
                    error_code = token_data.get("error")
                    raise CannotConnectException(
                        error_description
                        or error_code
                        or f"Auth0 token exchange failed: {token_response.status}"
                    )
        except aiohttp.ClientError as err:
            raise CannotConnectException("Auth0 token exchange request failed") from err

        return GeneracApiClient.with_expires_at(token_data)

    @staticmethod
    async def login_with_hosted_forms(
        session: aiohttp.ClientSession, username: str, password: str
    ) -> dict[str, Any]:
        """Complete Auth0 hosted login forms and exchange the PKCE callback."""
        pkce = Auth0PkceSession.create()
        callback_url = await Auth0PkceSession.submit_hosted_login(
            session, pkce["auth_url"], username, password
        )
        return await Auth0PkceSession.exchange_callback(
            session, callback_url, pkce["code_verifier"], pkce["state"]
        )

    @staticmethod
    async def submit_hosted_login(
        session: aiohttp.ClientSession, auth_url: str, username: str, password: str
    ) -> str:
        """Submit Auth0 hosted identifier/password forms and return callback URL."""
        try:
            response = await session.get(auth_url, allow_redirects=True)
        except aiohttp.ClientError as err:
            raise CannotConnectException("Auth0 hosted login request failed") from err
        for _ in range(8):
            page = await response.text()
            current_url = str(response.url)
            response.release()
            if GeneracApiClient._page_has_auth_error(page):
                raise InvalidCredentialsException()

            form = BeautifulSoup(page, features="html.parser").select_one("form")
            if form is None:
                raise CannotConnectException(
                    f"Auth0 hosted login form not found at {current_url}"
                )

            form_data = Auth0PkceSession._hosted_form_data(form, username, password)
            try:
                response = await session.post(
                    urljoin(
                        current_url,
                        form.attrs.get("action") or current_url,
                    ),
                    data=form_data,
                    allow_redirects=False,
                )
            except aiohttp.ClientError as err:
                raise CannotConnectException("Auth0 hosted login submit failed") from err
            if response.status >= 400:
                page = await response.text()
                response.release()
                if GeneracApiClient._page_has_auth_error(page):
                    raise InvalidCredentialsException()
                raise CannotConnectException(
                    f"Auth0 hosted login returned status {response.status}"
                )

            while response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if location.startswith("com.generac."):
                    response.release()
                    return location
                redirect_url = urljoin(str(response.url), location)
                response.release()
                try:
                    response = await session.get(
                        redirect_url, allow_redirects=False
                    )
                except aiohttp.ClientError as err:
                    raise CannotConnectException(
                        "Auth0 hosted login redirect failed"
                    ) from err

        response.release()
        raise CannotConnectException("Auth0 hosted login did not return a callback URL")

    @staticmethod
    def _hosted_form_data(form: Any, username: str, password: str) -> list[tuple[str, str]]:
        form_data = []
        for input_element in form.select("input[name]"):
            name = input_element.attrs["name"]
            field_type = input_element.attrs.get("type", "").lower()
            lower_name = name.lower()
            value = input_element.attrs.get("value", "")
            if field_type == "password" or "password" in lower_name:
                value = password
            elif (
                lower_name in ("username", "email", "login", "signinname")
                or "username" in lower_name
                or "email" in lower_name
            ):
                value = username
            form_data.append((name, value))
        return form_data

    @staticmethod
    def auth0_headers() -> dict[str, str]:
        """Return the Auth0 SDK headers used for token requests."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Auth0-Client": AUTH0_CLIENT_HEADER,
        }

    @staticmethod
    def _first(query: Mapping[str, list[str]], name: str) -> str:
        values = query.get(name, [])
        return values[0] if values else ""

    @staticmethod
    def _token_urlsafe(length: int) -> str:
        return secrets.token_urlsafe(length)[:length]

    @staticmethod
    def _code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class GeneracApiClient:
    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        access_token: str = "",
        refresh_token: str = "",
        expires_at: float = 0,
        token_update_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """MobileLink API Client for Generac."""
        self._username = username
        self._password = password
        self._session = session
        self._logged_in = False
        self._auth_method = ""
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self._token_update_callback = token_update_callback
        self.csrf = ""
        self._auth_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()

    async def async_get_data(self) -> dict[str, Item] | None:
        """Get data from the API."""
        async with self._auth_lock:
            try:
                if not self._logged_in:
                    await self.login_with_best_available_auth()
                    self._logged_in = True
                return await self.get_generator_data()
            except SessionExpiredException:
                self._logged_in = False
                _LOGGER.warning(
                    "Mobile Link rejected the Auth0 session; attempting token recovery"
                )

                if self.refresh_token and await self.refresh_tokens():
                    try:
                        self._logged_in = True
                        return await self.get_generator_data()
                    except SessionExpiredException:
                        self._logged_in = False
                        _LOGGER.warning(
                            "Mobile Link rejected the refreshed Auth0 token"
                        )

                if self._username and self._password:
                    try:
                        _LOGGER.info(
                            "Re-authenticating with Auth0 PKCE after token rejection"
                        )
                        await self.login_with_auth0_pkce()
                        self._logged_in = True
                        return await self.get_generator_data()
                    except InvalidCredentialsException:
                        raise
                    except (
                        AuthFlowUnavailableException,
                        CannotConnectException,
                        SessionExpiredException,
                        aiohttp.ClientError,
                    ) as exception:
                        self._logged_in = False
                        _LOGGER.warning(
                            "Auth0 PKCE re-authentication failed; trying cookie bridge: %s",
                            exception,
                        )

                    await self.login_with_mobile_link_web()
                    self._logged_in = True
                    return await self.get_generator_data()

                await self.login()
                self._logged_in = True
                return await self.get_generator_data()

    async def login_with_best_available_auth(self) -> None:
        """Use PKCE tokens first, then fall back to the web-cookie bridge."""
        if self.refresh_token:
            try:
                if self._token_needs_refresh():
                    await self.refresh_tokens_or_raise()
                self._auth_method = "auth0_pkce"
                return
            except (
                InvalidCredentialsException,
                CannotConnectException,
                aiohttp.ClientError,
            ) as err:
                _LOGGER.debug(
                    "Auth0 PKCE refresh failed; trying cookie bridge fallback: %s",
                    err,
                )
                self.access_token = ""
                self.refresh_token = ""

        if self.access_token:
            self._auth_method = "auth0_pkce"
            return

        if self._username and self._password:
            await self.login()
            return

        await self.login()

    async def get_generator_data(self):
        if self.uses_bearer_api:
            list_endpoint = "/Apparatus/list"
            details_endpoint = "/Apparatus/details/{}"
        else:
            list_endpoint = "/v2/Apparatus/list"
            details_endpoint = "/v1/Apparatus/details/{}"

        apparatuses = await self.get_endpoint(list_endpoint)
        if apparatuses is None:
            _LOGGER.debug("Could not decode apparatuses response")
            return None
        if not isinstance(apparatuses, list):
            raise CannotConnectException(
                f"Unexpected response from Generac endpoint {list_endpoint}"
            )

        data: dict[str, Item] = {}
        for apparatus in apparatuses:
            try:
                apparatus = from_dict(Apparatus, apparatus)
            except Exception as exception:
                raise CannotConnectException(
                    "Generac returned an invalid apparatus response"
                ) from exception
            if apparatus.type != 0:
                _LOGGER.debug(
                    "Unknown apparatus type %s %s", apparatus.type, apparatus.name
                )
                continue
            if apparatus.apparatusId is None:
                _LOGGER.warning("Generac returned an apparatus without an ID")
                continue
            detail_json = await self.get_endpoint(
                details_endpoint.format(apparatus.apparatusId)
            )
            if detail_json is None:
                _LOGGER.debug(
                    "Could not decode response from %s",
                    details_endpoint.format(apparatus.apparatusId),
                )
                continue
            try:
                detail = from_dict(ApparatusDetail, detail_json)
            except Exception as exception:
                raise CannotConnectException(
                    "Generac returned an invalid apparatus detail response"
                ) from exception
            data[str(apparatus.apparatusId)] = Item(apparatus, detail)
        return data

    async def get_endpoint(self, endpoint: str):
        try:
            api_base = API_V5_BASE if self.uses_bearer_api else API_BASE
            url = api_base + endpoint
            async with self._session.get(url, headers=self.headers) as response:
                if response.status == 204:
                    return None

                if response.status in (401, 403):
                    body = (await response.text())[:512]
                    is_waf_challenge = self._is_waf_challenge(body)
                    reason = (
                        "WAF challenge"
                        if is_waf_challenge
                        else "authorization rejected"
                    )
                    _LOGGER.warning(
                        "Mobile Link API rejected %s with HTTP %s (%s, server=%s, "
                        "request_id=%s)",
                        endpoint,
                        response.status,
                        reason,
                        response.headers.get("Server", ""),
                        response.headers.get("X-Request-Id", ""),
                    )
                    if is_waf_challenge:
                        raise CannotConnectException(
                            "Mobile Link API request was blocked by its WAF"
                        )
                    raise SessionExpiredException(
                        f"API session expired: {response.status}"
                    )

                if response.status >= 500:
                    raise CannotConnectException(
                        f"Mobile Link API returned HTTP {response.status}"
                    )

                if response.status != 200:
                    raise CannotConnectException(
                        f"Mobile Link API returned HTTP {response.status}"
                    )

                return await response.json(content_type=None)
        except SessionExpiredException:
            raise
        except CannotConnectException:
            raise
        except aiohttp.ClientError as exception:
            raise CannotConnectException("Unable to reach Mobile Link API") from exception
        except (TypeError, ValueError) as exception:
            raise CannotConnectException("Mobile Link API returned invalid JSON") from exception

    @property
    def headers(self) -> dict[str, str]:
        """Return auth headers for whichever login method is active."""
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": MOBILE_API_USER_AGENT,
        }
        if self.csrf:
            headers["X-Csrf-Token"] = self.csrf
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    @property
    def auth_method(self) -> str:
        """Return the authentication method currently serving API requests."""
        return self._auth_method

    @property
    def uses_bearer_api(self) -> bool:
        """Use the API v5 routes used by the current mobile application."""
        return bool(self.access_token)

    async def login(self) -> None:
        """Login to the Mobile Link API.

        Follow the APK's hosted Auth0 PKCE flow first, followed by the legacy
        Mobile Link web-cookie bridge when the bearer flow is unavailable.
        """
        self._auth_method = ""
        self._clear_bearer_tokens()
        self.csrf = ""

        if self._username and self._password:
            try:
                await self.login_with_auth0_pkce()
                return
            except AuthFlowUnavailableException as err:
                _LOGGER.debug("Auth0 PKCE login is not available: %s", err)
            except InvalidCredentialsException:
                raise
            except CannotConnectException as err:
                _LOGGER.debug("Auth0 PKCE login connection failed: %s", err)
            except aiohttp.ClientError as err:
                _LOGGER.debug("Auth0 PKCE login connection failed: %s", err)

        await self.login_with_mobile_link_web()

    async def login_with_auth0_pkce(self) -> None:
        """Complete the same hosted Auth0 PKCE login used by the Android APK."""
        if not self._username or not self._password:
            raise AuthFlowUnavailableException("PKCE login requires credentials")

        token_data = await Auth0PkceSession.login_with_hosted_forms(
            self._session, self._username, self._password
        )
        self._set_tokens(token_data)
        self._auth_method = "auth0_pkce"

    async def refresh_tokens(self) -> bool:
        """Refresh Auth0 tokens when token auth is active."""
        async with self._refresh_lock:
            if not self.refresh_token:
                _LOGGER.warning("Auth0 token refresh skipped because no refresh token is stored")
                return False

            try:
                async with self._session.post(
                    AUTH0_TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "client_id": AUTH0_CLIENT_ID,
                        "refresh_token": self.refresh_token,
                        "scope": AUTH0_SCOPE,
                        "audience": AUTH0_AUDIENCE,
                    },
                    headers=Auth0PkceSession.auth0_headers(),
                ) as token_response:
                    if token_response.status != 200:
                        _LOGGER.warning(
                            "Auth0 token refresh rejected with HTTP %s",
                            token_response.status,
                        )
                        self._clear_bearer_tokens()
                        return False

                    token_data = await self.safe_json(token_response)
            except aiohttp.ClientError as exception:
                _LOGGER.warning("Auth0 token refresh request failed: %s", exception)
                return False

            try:
                self._set_tokens(token_data)
            except AuthFlowUnavailableException:
                _LOGGER.warning("Auth0 token refresh returned no access token")
                self._clear_bearer_tokens()
                return False
            self._auth_method = "auth0_pkce"
            _LOGGER.info("Auth0 access token refreshed successfully")
            return True

    async def refresh_tokens_or_raise(self) -> None:
        if not await self.refresh_tokens():
            raise InvalidCredentialsException("Auth0 refresh token was rejected")

    def _set_tokens(self, token_data: Mapping[str, Any]) -> None:
        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthFlowUnavailableException("Auth0 response did not include token")

        self.access_token = str(access_token)
        refresh_token = token_data.get("refresh_token")
        if refresh_token:
            self.refresh_token = str(refresh_token)
        expires_at = token_data.get("expires_at")
        if expires_at is not None:
            self.expires_at = float(expires_at)
        elif token_data.get("expires_in") is not None:
            self.expires_at = time.time() + float(token_data["expires_in"]) - 60
        else:
            token_exp = self._jwt_exp(self.access_token)
            if token_exp is not None:
                self.expires_at = token_exp

        if self._token_update_callback is not None:
            self._token_update_callback(
                {
                    CONF_AUTH_MODE: AUTH_MODE_PKCE,
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.expires_at,
                }
            )

    def _clear_bearer_tokens(self) -> None:
        """Clear persisted bearer credentials before using the cookie bridge."""
        had_tokens = bool(self.access_token or self.refresh_token or self.expires_at)
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = 0
        if had_tokens and self._token_update_callback is not None:
            self._token_update_callback(
                {
                    CONF_AUTH_MODE: AUTH_MODE_WEB_COOKIE,
                    "access_token": "",
                    "refresh_token": "",
                    "expires_at": 0,
                }
            )

    async def login_with_mobile_link_web(self) -> None:
        """Login through Mobile Link's Auth0 web bridge and keep API cookies."""
        self._clear_bearer_tokens()
        self._auth_method = ""
        self.csrf = ""
        try:
            response = await self._session.get(
                f"{AUTH0_SIGN_IN}?{urlencode({'userEmail': self._username})}",
                allow_redirects=True,
            )
        except aiohttp.ClientError as err:
            raise CannotConnectException("Unable to open Mobile Link login") from err

        for _ in range(4):
            if self._is_mobile_link_app_url(str(response.url)):
                response.release()
                self._auth_method = "mobile_link_cookie"
                return

            page = await response.text()
            response_url = str(response.url)
            response.release()
            if self._page_has_auth_error(page):
                raise InvalidCredentialsException()

            form = BeautifulSoup(page, features="html.parser").select_one("form")
            if form is None:
                _LOGGER.debug("Could not find Auth0 login form at %s", response_url)
                raise CannotConnectException("Unable to find Auth0 login form")

            response = await self.submit_form(
                response_url,
                form,
                {
                    "email": self._username,
                    "username": self._username,
                    "password": self._password,
                },
            )

        response.release()
        raise CannotConnectException("Auth0 login did not complete")

    def _token_needs_refresh(self) -> bool:
        if not self.access_token:
            return True

        token_exp = self._jwt_exp(self.access_token)
        if token_exp is not None:
            return time.time() >= token_exp - TOKEN_EXPIRY_SKEW

        return self.expires_at > 0 and time.time() >= self.expires_at

    @staticmethod
    def _jwt_exp(access_token: str) -> float | None:
        """Return a JWT expiration timestamp without validating the signature."""
        try:
            payload = access_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
            expiration = json.loads(decoded).get("exp")
            return float(expiration) if expiration is not None else None
        except (
            IndexError,
            UnicodeDecodeError,
            ValueError,
            TypeError,
            binascii.Error,
            json.JSONDecodeError,
        ):
            return None

    @staticmethod
    async def safe_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            data = await response.json(content_type=None)
        except (aiohttp.ClientError, TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def with_expires_at(token_data: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(token_data)
        expires_in = result.get("expires_in")
        if expires_in and "expires_at" not in result:
            result["expires_at"] = time.time() + float(expires_in) - 60
        return result

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

    @staticmethod
    def _is_waf_challenge(body: str) -> bool:
        """Identify the Incapsula response without logging its HTML body."""
        lowered = body.lower()
        return "_incapsula_resource" in lowered or "noindex, nofollow" in lowered

    async def submit_form(
        self,
        response_url: str,
        form: Any,
        overrides: Mapping[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        """Submit an HTML form while preserving hidden Auth0 fields."""
        if form is None:
            raise CannotConnectException("Could not find login form")

        action = form.attrs.get("action")
        if action is None:
            action = response_url

        form_data = []
        overrides = overrides or {}
        for input_element in form.select("input[name]"):
            name = input_element.attrs["name"]
            form_data.append((name, self._form_value(name, input_element, overrides)))

        try:
            login_response = await self._session.post(
                urljoin(response_url, action),
                data=form_data,
                allow_redirects=True,
            )
        except aiohttp.ClientError as exception:
            raise CannotConnectException("Mobile Link login submit failed") from exception

        if login_response.status >= 400:
            page = await login_response.text()
            login_response.release()
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
