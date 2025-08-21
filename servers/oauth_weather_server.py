"""
Run from the repository root:
    uv run servers/oauth_weather_server.py
"""

import jwt
import aiohttp
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import AnyHttpUrl
import random
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import os
from dotenv import load_dotenv
load_dotenv()

# Configuration - replace with your actual tenant and client IDs
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
SCOPES = os.getenv("SCOPES")
REQUIRED_SCOPES = [f"api://{CLIENT_ID}/{SCOPE}" for SCOPE in SCOPES.split(",")]

print(f"Using Tenant ID: {TENANT_ID}")
print(f"Using Client ID: {CLIENT_ID}")
print(f"Required Scopes: {REQUIRED_SCOPES}")

class EntraIdTokenVerifier(TokenVerifier):
  """JWT token verifier for Entra ID (Azure AD)."""

  def __init__(self, tenant_id: str, client_id: str):
    self.tenant_id = tenant_id
    self.client_id = client_id
    self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    self.jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    self._jwks_cache: Optional[Dict[str, Any]] = None
    self._cache_expiry: Optional[datetime] = None

  async def _get_jwks(self) -> Dict[str, Any]:
    """Fetch JWKS from Entra ID with caching."""
    now = datetime.now(timezone.utc)

    # Return cached JWKS if still valid (cache for 1 hour)
    if (self._jwks_cache and self._cache_expiry and
            now < self._cache_expiry):
      return self._jwks_cache

    try:
      async with aiohttp.ClientSession() as session:
        async with session.get(self.jwks_uri) as response:
          if response.status == 200:
            jwks = await response.json()
            self._jwks_cache = jwks
            self._cache_expiry = now.replace(hour=now.hour + 1)
            return jwks
          else:
            raise Exception(f"Failed to fetch JWKS: {response.status}")
    except Exception as e:
      print(f"Error fetching JWKS: {e}")
      raise

  def _get_signing_key(self, token_header: Dict[str, Any], jwks: Dict[str, Any]) -> str:
    """Extract the signing key from JWKS based on token header."""
    kid = token_header.get('kid')
    if not kid:
      raise jwt.InvalidTokenError("Token header missing 'kid'")

    for key in jwks.get('keys', []):
      if key.get('kid') == kid:
        # Convert JWK to PEM format for PyJWT
        return jwt.algorithms.RSAAlgorithm.from_jwk(key)

    raise jwt.InvalidKeyError(f"Unable to find signing key with kid: {kid}")

  async def verify_token(self, token: str) -> AccessToken | None:
    """Verify JWT token from Entra ID."""
    try:
      # Decode token header to get key ID
      token_header = jwt.get_unverified_header(token)

      # Get JWKS
      jwks = await self._get_jwks()

      # Get signing key
      signing_key = self._get_signing_key(token_header, jwks)

      # Verify and decode token
      payload = jwt.decode(
          token,
          signing_key,
          algorithms=['RS256'],
          audience=self.client_id,
          issuer=self.issuer,
          options={
              "verify_signature": True,
              "verify_exp": True,
              "verify_aud": True,
              "verify_iss": True,
          }
      )

      print(f"Token payload: {payload}")

      # Extract scopes from token
      raw_scopes = payload.get('scp', '').split() or payload.get('roles', [])
      scopes = [f"api://{self.client_id}/{scope}" for scope in raw_scopes]

      return AccessToken(
          token=token,
          client_id=self.client_id,
          scopes=scopes,
          expires_at=payload.get('exp')
      )

    except jwt.ExpiredSignatureError:
      print("Token has expired")
      return None
    except jwt.InvalidAudienceError:
      print("Token has invalid audience")
      return None
    except jwt.InvalidIssuerError:
      print("Token has invalid issuer")
      return None
    except jwt.InvalidTokenError as e:
      print(f"Invalid token: {e}")
      return None
    except Exception as e:
      print(f"Token verification failed: {e}")
      return None


# Create FastMCP instance as a Resource Server
mcp = FastMCP(
    "Weather Service",
    # JWT token verifier for Entra ID authentication
    token_verifier=EntraIdTokenVerifier(TENANT_ID, CLIENT_ID),
    # Auth settings for RFC 9728 Protected Resource Metadata
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(
            f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"),
        resource_server_url=AnyHttpUrl(
            "http://localhost:8000/mcp"),
        required_scopes=REQUIRED_SCOPES,
    ),
)


@mcp.tool()
async def get_weather(city: str = "London") -> dict[str, str]:
  """Get weather data for a city"""
  temperatures = ["15", "18", "20", "22", "25", "28", "30", "12", "8", "5"]
  conditions = ["Sunny", "Partly cloudy", "Cloudy",
                "Rainy", "Stormy", "Clear", "Foggy", "Windy", "Snowy"]
  humidity_levels = ["30%", "45%", "55%", "60%",
                     "65%", "70%", "75%", "80%", "85%", "90%"]

  return {
      "city": city,
      "temperature": random.choice(temperatures),
      "condition": random.choice(conditions),
      "humidity": random.choice(humidity_levels),
  }


# https://github.com/modelcontextprotocol/python-sdk/issues/1264
# https://github.com/modelcontextprotocol/python-sdk/pull/1288
@mcp.custom_route("/mcp/.well-known/oauth-protected-resource", methods=["GET"])
async def custom_well_known_endpoint(request: Request) -> Response:
  """
  Custom .well-known/oauth-protected-resource endpoint that correctly advertises the SSE endpoint
  as the protected resource while serving the .well-known endpoint at the root.
  """
  return JSONResponse({
      "resource": "http://localhost:8000/mcp",
      "authorization_servers": [
          f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
      ],
      "scopes_supported": REQUIRED_SCOPES,
      "bearer_methods_supported": ["header"]
  })

if __name__ == "__main__":
  mcp.run(transport="streamable-http")
