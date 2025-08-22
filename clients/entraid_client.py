"""
Before running, specify running MCP server URL. For example
    uv run servers/entraid_weather_server.py

Then run:
    uv run clients/entraid_client.py
"""

import os
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import msal
import httpx
import time
from typing import Dict, List, Optional, AsyncGenerator
from dotenv import load_dotenv
import threading
from urllib.parse import urljoin
from mcp.shared.auth import ProtectedResourceMetadata
from mcp.client.streamable_http import MCP_PROTOCOL_VERSION
from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import ValidationError
import re

load_dotenv()


class EntraIDDeviceCodeAuth(httpx.Auth):
  """Microsoft Entra ID Device Code auth for httpx.Auth."""

  requires_response_body = True

  def __init__(
      self,
      client_id: str,
      server_url: Optional[str] = None,
  ) -> None:
    self.client_id = client_id
    self.server_url = server_url
    self.scopes: List[str] = []
    self.auth_server_url: Optional[str] = None

    self._pca = None
    self._token = None
    self._expires_on = 0
    self._cache = msal.SerializableTokenCache()
    self._lock = threading.Lock()

  def _require_pca(self) -> None:
    """Ensure MSAL client is initialized."""
    if not self._pca:
      raise RuntimeError("MSAL client not initialized.")

  def _acquire_silent(self) -> Optional[Dict]:
    self._require_pca()
    accounts = self._pca.get_accounts()
    return self._pca.acquire_token_silent(self.scopes, account=accounts[0]) if accounts else None

  def _acquire_with_device_code(self) -> Dict:
    self._require_pca()
    flow = self._pca.initiate_device_flow(scopes=self.scopes)
    if "user_code" not in flow:
      raise RuntimeError("Device code authentication failed.")
    print(flow["message"], flush=True)
    result = self._pca.acquire_token_by_device_flow(
        flow)  # blocks until complete or timeout
    if not result or "access_token" not in result:
      raise RuntimeError("Device code authentication failed.")
    return result

  def _extract_resource_metadata_from_www_auth(self, init_response: httpx.Response) -> str | None:
    """
    Extract protected resource metadata URL from WWW-Authenticate header as per RFC9728.
    """
    if not init_response or init_response.status_code != 401:
      return None
    www_auth_header = init_response.headers.get("WWW-Authenticate")
    if not www_auth_header:
      return None
    pattern = r'resource_metadata=(?:"([^"]+)"|([^\s,]+))'
    match = re.search(pattern, www_auth_header)
    return (match.group(1) or match.group(2)) if match else None

  async def _discover_protected_resource(self, init_response: httpx.Response) -> httpx.Request:
    # RFC9728: Try to extract resource_metadata URL from WWW-Authenticate header of the initial response
    url = self._extract_resource_metadata_from_www_auth(init_response)
    if not url:
      # Fallback to well-known discovery using server_url origin as base
      url = urljoin(self.server_url, "/.well-known/oauth-protected-resource")
    return httpx.Request("GET", url, headers={MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION})

  async def _handle_protected_resource_response(self, response: httpx.Response) -> None:
    """Handle discovery response and initialize MSAL PCA once successful."""
    if response.status_code != 200:
      return
    try:
      content = await response.aread()
      metadata = ProtectedResourceMetadata.model_validate_json(content)
    except ValidationError:
      return

    if metadata.authorization_servers:
      auth_server_url = str(metadata.authorization_servers[0])
      if auth_server_url.endswith('/v2.0'):
        auth_server_url = auth_server_url[:-5]
      self.auth_server_url = auth_server_url
    if metadata.scopes_supported:
      self.scopes = metadata.scopes_supported

    if not self._pca:
      authority = self.auth_server_url or self.server_url
      if not self.client_id or not authority:
        raise RuntimeError("Cannot initialize MSAL.")
      self._pca = msal.PublicClientApplication(
          client_id=self.client_id,
          authority=authority,
          token_cache=self._cache,
      )

  def _token_valid(self) -> bool:
    return bool(self._token and (time.time() < (self._expires_on - 60)))

  def _ensure_token(self, force_interactive: bool = False) -> None:
    """
    Ensure a valid token is available, acquiring one if needed.
    Try silent acquisition first, then interactive device code if needed.
    """
    with self._lock:
      if force_interactive or not self._token_valid():
        result = None if force_interactive else self._acquire_silent()
        if not result or "access_token" not in result:
          result = self._acquire_with_device_code()
        self._token = result["access_token"]
        self._expires_on = int(result.get("expires_on", time.time() + 300))

  def _apply_auth(self, request: httpx.Request) -> None:
    if self._token:
      request.headers["Authorization"] = f"Bearer {self._token}"

  async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
    if self._pca:
      self._ensure_token(force_interactive=False)
    self._apply_auth(request)
    response = yield request

    if response.status_code == 401:
      discovery_request = await self._discover_protected_resource(response)
      discovery_response = yield discovery_request
      await self._handle_protected_resource_response(discovery_response)

      self._ensure_token(force_interactive=True)
      self._apply_auth(request)
      yield request


async def main():
  client_id = os.getenv("CLIENT_ID")
  if not client_id:
    print("CLIENT_ID is not set. Export it before running.")
    raise SystemExit(2)

  entraid_auth = EntraIDDeviceCodeAuth(
      client_id=client_id,
      server_url="http://localhost:8000/mcp"
  )

  async with streamablehttp_client("http://localhost:8000/mcp", auth=entraid_auth) as (read, write, _):
    async with ClientSession(read, write) as session:
      await session.initialize()
      tools = await session.list_tools()
      print(f"Available tools: {[tool.name for tool in tools.tools]}")
      resources = await session.list_resources()
      print(f"Available resources: {[r.uri for r in resources.resources]}")


if __name__ == "__main__":
  asyncio.run(main())
