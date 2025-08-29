"""
Run from the repository root:
    uv run servers/entraid_obo_server.py
"""
import jwt
import aiohttp
import random
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import AnyHttpUrl
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("entraid_obo_server")

# Configuration
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SCOPES = os.getenv("SCOPES", "").split(",")
REQUIRED_SCOPES = [f"api://{CLIENT_ID}/{scope}" for scope in SCOPES]
ISSUER_URL = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
GRAPH_TOKEN_ENDPOINT = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH_SCOPE = os.getenv("GRAPH_SCOPE", "https://graph.microsoft.com/.default")
GRAPH_ME_URL = os.getenv("GRAPH_ME_URL", "https://graph.microsoft.com/v1.0/me")


class EntraIdTokenVerifier(TokenVerifier):
  """JWT token verifier for Entra ID."""

  def __init__(self, tenant_id: str, client_id: str):
    self.tenant_id = tenant_id
    self.client_id = client_id
    self.jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    self._jwks_cache: Optional[Dict[str, Any]] = None
    self._cache_expiry: Optional[datetime] = None

  async def _get_jwks(self) -> Dict[str, Any]:
    """Fetch JWKS with 1-hour caching."""
    now = datetime.now(timezone.utc)

    if self._jwks_cache and self._cache_expiry and now < self._cache_expiry:
      return self._jwks_cache

    async with aiohttp.ClientSession() as session:
      async with session.get(self.jwks_uri) as response:
        if response.status != 200:
          raise Exception(f"JWKS fetch failed: {response.status}")

        self._jwks_cache = await response.json()
        self._cache_expiry = now.replace(hour=now.hour + 1)
        return self._jwks_cache

  async def verify_token(self, token: str) -> AccessToken | None:
    """Verify JWT token from Entra ID."""
    logger.debug(f"Verifying token: {token}")
    try:
      header = jwt.get_unverified_header(token)
      kid = header.get('kid')
      if not kid:
        raise jwt.InvalidTokenError("Missing 'kid' in token header")

      jwks = await self._get_jwks()

      # Find signing key
      signing_key = None
      for key in jwks.get('keys', []):
        if key.get('kid') == kid:
          signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
          break

      if not signing_key:
        raise jwt.InvalidKeyError(f"Signing key not found: {kid}")

      # Verify token
      payload = jwt.decode(
          token, signing_key, algorithms=['RS256'],
          audience=self.client_id, issuer=ISSUER_URL,
          options={"verify_signature": True, "verify_exp": True,
                   "verify_aud": True, "verify_iss": True}
      )

      # Extract scopes
      raw_scopes = payload.get('scp', '').split() or payload.get('roles', [])
      scopes = [f"api://{self.client_id}/{scope}" for scope in raw_scopes]

      return AccessToken(
          token=token,
          client_id=self.client_id,
          scopes=scopes,
          expires_at=payload.get('exp')
      )

    except (jwt.ExpiredSignatureError, jwt.InvalidAudienceError,
            jwt.InvalidIssuerError, jwt.InvalidTokenError) as e:
      logger.error(f"Token verification failed: {e}")
      return None


def _get_bearer_token(ctx):
  request = ctx.request_context.request
  # Check if 'Authorization' header is present
  authorization_header = request.headers.get("Authorization")

  if authorization_header:
      # Split the header into 'Bearer <token>'
    parts = authorization_header.split()

    if len(parts) == 2 and parts[0] == 'Bearer':
      return parts[1]
    else:
      raise ValueError("Invalid Authorization header format")
  else:
    raise ValueError("Authorization header missing")


# New: OBO helper to get Graph access token using incoming access token
async def _get_graph_token_on_behalf_of(assertion_token: str) -> str:
  if not CLIENT_SECRET:
    raise RuntimeError("CLIENT_SECRET is not configured for OBO flow")

  data = {
      "client_id": CLIENT_ID,
      "client_secret": CLIENT_SECRET,
      "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
      "requested_token_use": "on_behalf_of",
      "scope": GRAPH_SCOPE,
      "assertion": assertion_token,
  }

  async with aiohttp.ClientSession() as session:
    async with session.post(GRAPH_TOKEN_ENDPOINT, data=data) as resp:
      body = await resp.json()
      if resp.status != 200:
        logger.error(f"OBO token exchange failed ({resp.status}): {body}")
        raise RuntimeError("Failed to obtain Graph access token via OBO")
      return body["access_token"]


# Initialize FastMCP
mcp = FastMCP(
    "Weather Service",
    token_verifier=EntraIdTokenVerifier(TENANT_ID, CLIENT_ID),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(ISSUER_URL),
        resource_server_url=AnyHttpUrl("http://localhost:9000/mcp"),
        required_scopes=REQUIRED_SCOPES,
    ),
    port = 9000
)


@mcp.tool()
async def whoami(ctx: Context) -> dict[str, str]:
  """Return the user's Microsoft Graph profile using OBO."""
  token = _get_bearer_token(ctx)

  # Exchange incoming token for a Graph token (OBO)
  graph_token = await _get_graph_token_on_behalf_of(token)

  # Call Graph /me
  async with aiohttp.ClientSession() as session:
    async with session.get(
        GRAPH_ME_URL,
        headers={"Authorization": f"Bearer {graph_token}"}
    ) as resp:
      data = await resp.json()
      if resp.status != 200:
        logger.error(f"Graph /me call failed ({resp.status}): {data}")
        raise RuntimeError("Failed to retrieve user profile from Graph")

  # Return common profile fields as strings
  return {
      "id": str(data.get("id", "")),
      "displayName": str(data.get("displayName", "")),
      "userPrincipalName": str(data.get("userPrincipalName", "")),
      "givenName": str(data.get("givenName", "")),
      "surname": str(data.get("surname", "")),
      "mail": str(data.get("mail", "")),
  }


@mcp.custom_route("/mcp/.well-known/oauth-protected-resource", methods=["GET"])
async def custom_well_known_endpoint(request: Request) -> Response:
  """OAuth protected resource metadata endpoint."""
  return JSONResponse({
      "resource": "http://localhost:9000/mcp",
      "authorization_servers": [ISSUER_URL],
      "scopes_supported": REQUIRED_SCOPES,
      "bearer_methods_supported": ["header"]
  })

if __name__ == "__main__":
  mcp.run(transport="streamable-http")
