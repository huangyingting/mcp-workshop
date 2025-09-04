"""
Run from the repository root:
    uv run mcp run servers/simple_stock_server.py -t streamable-http, or
    uv run mcp dev servers/simple_stock_server.py, or
    uv run servers/simple_stock_server.py -t streamable-http
"""
import jwt
import aiohttp
import os
from typing import Dict, Any, Optional
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession
from mcp.types import SamplingMessage, TextContent
from mcp.server.fastmcp.prompts import base
import argparse
import logging
from pydantic import BaseModel, Field
import pandas as pd
from datetime import datetime, timedelta, timezone
import random
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("simple_stock_server")

MOCK_STOCK_DATA = {
    "AAPL": {"price": 175.50, "name": "Apple Inc.", "sector": "Technology", "market_cap": 2800000000000, "pe_ratio": 28.5, "dividend_yield": 0.0048},
    "MSFT": {"price": 509.77, "name": "Microsoft Corporation", "sector": "Technology", "market_cap": 3790000000000, "pe_ratio": 37.32, "dividend_yield": 0.65},
    "GOOGL": {"price": 138.25, "name": "Alphabet Inc.", "sector": "Technology", "market_cap": 1750000000000, "pe_ratio": 24.8, "dividend_yield": 0.0},
    "AMZN": {"price": 145.80, "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "market_cap": 1520000000000, "pe_ratio": 42.1, "dividend_yield": 0.0},
    "TSLA": {"price": 215.99, "name": "Tesla Inc.", "sector": "Consumer Discretionary", "market_cap": 687000000000, "pe_ratio": 58.3, "dividend_yield": 0.0},
    "META": {"price": 325.45, "name": "Meta Platforms Inc.", "sector": "Technology", "market_cap": 850000000000, "pe_ratio": 23.7, "dividend_yield": 0.0035},
    "NVDA": {"price": 445.32, "name": "NVIDIA Corporation", "sector": "Technology", "market_cap": 1100000000000, "pe_ratio": 65.2, "dividend_yield": 0.0012}
}

# Configuration
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
SCOPES = os.getenv("SCOPES", "").split(",")
REQUIRED_SCOPES = [f"api://{CLIENT_ID}/{scope}" for scope in SCOPES]
ISSUER_URL = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"


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


mcp = FastMCP("simple_stock_server")

def generate_mock_historical_data(symbol: str, period: str = "1mo") -> pd.DataFrame:
  """Generate mock historical stock data for a given symbol and time period."""
  if symbol not in MOCK_STOCK_DATA:
    return pd.DataFrame()

  base_price = MOCK_STOCK_DATA[symbol]["price"]
  days = {"1d": 1, "1mo": 30, "3mo": 90, "1y": 365}.get(period, 30)
  
  dates = [datetime.now() - timedelta(days=i) for i in range(days, 0, -1)]
  current_price = base_price * 0.95
  prices = []
  
  for _ in dates:
    current_price *= (1 + random.uniform(-0.02, 0.02))
    prices.append(current_price)
  
  prices[-1] = base_price
  
  return pd.DataFrame({
      "Open": [p * random.uniform(0.99, 1.01) for p in prices],
      "High": [p * random.uniform(1.005, 1.03) for p in prices],
      "Low": [p * random.uniform(0.97, 0.995) for p in prices],
      "Close": prices,
      "Volume": [random.randint(50000000, 200000000) for _ in prices]
  }, index=dates)

def get_performance_summary(symbol: str, period: str) -> str:
  """Build a concise performance summary string for a stock over the given period."""
  try:
    data = generate_mock_historical_data(symbol, period)
    if data.empty:
      price = get_stock_price(symbol)
      return f"No recent history for {symbol} over {period}. Latest known price ${price:.2f}." if price >= 0 else f"No data available for {symbol}."
    
    first, last = float(data["Close"].iloc[0]), float(data["Close"].iloc[-1])
    change = last - first
    pct = (change / first) * 100 if first else 0.0
    return f"{symbol} {change:+.2f} ({pct:+.2f}%) over {period}. Latest close ${last:.2f}."
  except Exception as e:
    return f"Error gathering data for {symbol}: {e}"

@mcp.resource("stock://{symbol}")
def stock_resource(symbol: str) -> str:
  """Expose stock price data as a resource."""
  price = get_stock_price(symbol)
  return f"The current price of '{symbol}' is ${price:.2f}." if price >= 0 else f"Error: Could not retrieve price for symbol '{symbol}'."

@mcp.resource("stock://tickers")
def tickers_resource() -> str:
  """Return a list of available stock tickers."""
  return "AAPL, MSFT, GOOGL, AMZN, TSLA, META, NVDA"

@mcp.prompt("stock_analysis_prompt")
def stock_analysis(symbol: str, period: str = "1mo"):
  """Build a prompt for analyzing a stock's recent performance."""
  summary = get_performance_summary(symbol, period)
  return [base.UserMessage(f"You are a concise financial analysis assistant. Provide a short analysis of {symbol}. Context: {summary} Discuss trend, momentum, and any notable risk.")]

@mcp.tool()
def get_stock_price(symbol: str) -> float:
  """Retrieve the current stock price for the given ticker symbol."""
  try:
    return float(MOCK_STOCK_DATA[symbol]["price"]) if symbol in MOCK_STOCK_DATA else -1.0
  except Exception:
    return -1.0

@mcp.tool()
def get_stock_history(symbol: str, period: str = "1mo") -> str:
  """Retrieve historical data for a stock as CSV formatted string."""
  try:
    data = generate_mock_historical_data(symbol, period)
    return data.to_csv() if not data.empty else f"No historical data found for symbol '{symbol}' with period '{period}'."
  except Exception as e:
    return f"Error fetching historical data: {str(e)}"

@mcp.tool()
def compare_stock_prices(symbol1: str, symbol2: str) -> str:
  """Compare the current stock prices of two ticker symbols."""
  price1, price2 = get_stock_price(symbol1), get_stock_price(symbol2)
  if price1 < 0 or price2 < 0:
    return f"Error: Could not retrieve data for comparison of '{symbol1}' and '{symbol2}'."
  
  if price1 == price2:
    return f"Both {symbol1} and {symbol2} have the same price (${price1:.2f})."
  
  higher, lower = (symbol1, symbol2) if price1 > price2 else (symbol2, symbol1)
  higher_price, lower_price = max(price1, price2), min(price1, price2)
  return f"{higher} (${higher_price:.2f}) is higher than {lower} (${lower_price:.2f})."

@mcp.tool()
async def stock_headline_sampling(symbol: str, ctx: Context[ServerSession, None]) -> str:
  """Use MCP sampling to generate a market-style headline for the given stock."""
  context = get_performance_summary(symbol, "1mo")
  result = await ctx.session.create_message(
      messages=[SamplingMessage(role="user", content=TextContent(type="text", text=f"Create a stock headline based on the following data\n{context}"))],
      max_tokens=100,
  )
  return result.content.text if result.content.type == "text" else str(result.content)

def _humanize_number(n: float | int | None) -> str:
  """Format large numbers in human-readable format (e.g., 1.23T, 456.7B)."""
  try:
    if n is None:
      return "n/a"
    n = float(n)
    for suffix, div in [("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)]:
      if abs(n) >= div:
        return f"{n/div:.2f}{suffix}"
    return f"{n:.2f}"
  except Exception:
    return "n/a"

class WeekRangePreference(BaseModel):
  """Schema for asking whether to include 52-week range information."""
  include_week_range: bool = Field(default=False, description="Whether to include 52-week high/low information")

@mcp.tool()
async def get_ticker_info(symbol: str, ctx: Context[ServerSession, None]) -> str:
  """Get comprehensive information for a ticker symbol with optional 52-week range."""
  result = await ctx.elicit(message="Would you like to include 52-week high/low information?", schema=WeekRangePreference)
  include_week_range = result.action == "accept" and result.data and result.data.include_week_range

  try:
    if symbol not in MOCK_STOCK_DATA:
      return f"No information available for '{symbol}'"

    data = MOCK_STOCK_DATA[symbol]
    market_cap = _humanize_number(data["market_cap"])
    pe_display = f"{data['pe_ratio']:.2f}" if data["pe_ratio"] else "n/a"
    
    result_str = f"""{data['name']} ({symbol})
Price: ${data['price']:.2f} USD
Market Cap: {market_cap}
PE Ratio: {pe_display}
Dividend Yield: {data['dividend_yield'] * 100:.2f}%
Sector: {data['sector']}"""

    if include_week_range:
      week_low, week_high = data['price'] * 0.75, data['price'] * 1.25
      result_str += f"\n52W Range: ${week_low:.2f} - ${week_high:.2f}"

    return result_str
  except Exception as e:
    return f"Error fetching info for '{symbol}': {e}"


@mcp.tool()
def calculate_portfolio_value(holdings: dict[str, int]) -> str:
    """
    Calculate total portfolio value.
    holdings: dict mapping stock symbols to share counts
    """
    try:
        if not isinstance(holdings, dict) or not holdings:
            return "Error: Provide a non-empty dict of holdings like {'AAPL': 10, 'MSFT': 5}."

        lines: list[str] = []
        total = 0.0
        errors: list[str] = []

        for sym, shares in holdings.items():
            symbol = str(sym).upper().strip()
            if not symbol:
                errors.append(f"Invalid symbol key: {sym!r}")
                continue
            if not isinstance(shares, int):
                errors.append(f"{symbol}: share count must be an int, got {type(shares).__name__}")
                continue
            if shares < 0:
                errors.append(f"{symbol}: negative share count not allowed")
                continue

            price = get_stock_price(symbol)
            if price < 0:
                errors.append(f"{symbol}: unknown symbol")
                continue

            value = shares * price
            total += value
            lines.append(f"{symbol}: {shares} @ ${price:.2f} = ${value:.2f}")

        summary = "\n".join(lines) if lines else "No valid holdings."
        summary += f"\nTotal: ${total:.2f}"
        if errors:
            summary += "\nNotes: " + "; ".join(errors)
        return summary
    except Exception as e:
        return f"Error calculating portfolio value: {e}"

@mcp.resource("stock://sectors")
def sectors_resource() -> str:
    """Return available market sectors."""
    try:
        sectors = sorted({info.get("sector", "").strip() for info in MOCK_STOCK_DATA.values() if info.get("sector")})
        return ", ".join(sectors) if sectors else "No sectors available."
    except Exception as e:
        return f"Error retrieving sectors: {e}"

@mcp.prompt("risk_assessment_prompt")
def risk_assessment(symbol: str, risk_tolerance: str):
    """Generate a risk assessment prompt."""
    tol = (risk_tolerance or "").strip().lower()
    tol_norm = tol if tol in {"conservative", "moderate", "aggressive"} else "moderate"

    tol_briefs = {
        "conservative": "prioritize capital preservation and low drawdowns; avoid high volatility and speculative exposure",
        "moderate": "balance growth and stability; tolerate moderate volatility with prudent risk controls",
        "aggressive": "seek higher growth; accept higher volatility and drawdown risk with active risk management",
    }

    if symbol not in MOCK_STOCK_DATA:
        brief = tol_briefs[tol_norm]
        content = (
            f"You are a concise portfolio risk assistant.\n"
            f"Ticker '{symbol}' is unknown. Provide a short risk checklist for a {tol_norm} investor ({brief}).\n"
            "- List 3-5 key risk factors to consider (market, sector, company, valuation, liquidity).\n"
            "- Suggest a rough position sizing guideline (% of portfolio) for this tolerance.\n"
            "- Offer 1-2 risk management tips (time horizon, stop-loss, diversification).\n"
            "Keep it to 6-8 lines. Avoid boilerplate and disclaimers."
        )
        return [base.UserMessage(content)]

    data = MOCK_STOCK_DATA[symbol]
    name = data.get("name", symbol)
    price = data.get("price")
    sector = data.get("sector", "n/a")
    market_cap = _humanize_number(data.get("market_cap"))
    pe_display = f"{data.get('pe_ratio'):.2f}" if data.get("pe_ratio") else "n/a"
    div_yield = f"{(data.get('dividend_yield') or 0.0) * 100:.2f}%"
    perf = get_performance_summary(symbol, "1mo")
    brief = tol_briefs[tol_norm]

    content = (
        f"You are a concise portfolio risk assistant. Assess risk for {name} ({symbol}) "
        f"for a {tol_norm} investor ({brief}).\n"
        f"- Sector: {sector}\n"
        f"- Price: ${price:.2f} | Market Cap: {market_cap} | P/E: {pe_display} | Dividend: {div_yield}\n"
        f"- Recent performance: {perf}\n\n"
        "Return:\n"
        "1) Top risk factors (3-5 bullets max)\n"
        "2) Volatility expectation (Low/Med/High) and why\n"
        "3) Suggested position sizing range (% of portfolio) for this tolerance\n"
        "4) Risk management tips (e.g., stop-loss or time horizon)\n"
        "5) Overall risk rating (Low/Med/High)\n"
        "Keep it to 6-8 lines. No disclaimers."
    )
    return [base.UserMessage(content)]

class InvestmentPreference(BaseModel):
    risk_level: str = Field(description="low, medium, or high")
    time_horizon: str = Field(description="short, medium, or long-term")

@mcp.tool()
async def get_investment_advice(symbol: str, ctx: Context[ServerSession, None]) -> str:
    """Provide investment advice based on user preferences."""
    # Gather user preferences
    result = await ctx.elicit(
        message="Share investment preferences (risk_level: low/medium/high; time_horizon: short/medium/long-term).",
        schema=InvestmentPreference,
    )
    # Defaults if user declines or incomplete
    risk_raw = (getattr(result.data, "risk_level", None) if result.action == "accept" and result.data else None) or "medium"
    horizon_raw = (getattr(result.data, "time_horizon", None) if result.action == "accept" and result.data else None) or "medium"

    risk = str(risk_raw).strip().lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"

    hr = str(horizon_raw).strip().lower()
    if hr in {"short", "short-term"}:
        horizon = "short"
    elif hr in {"medium", "mid", "mid-term"}:
        horizon = "medium"
    elif hr in {"long", "long-term"}:
        horizon = "long-term"
    else:
        horizon = "medium"

    # Unknown ticker handling
    if symbol not in MOCK_STOCK_DATA:
        return (
            f"'{symbol}' is not available. Preferences: risk={risk}, horizon={horizon}.\n"
            "- Use diversified exposure to the target theme/sector.\n"
            "- Position size: low 1-3%, medium 3-6%, high 5-10% of portfolio.\n"
            "- Controls: set max drawdown, stagger entries (DCA), review quarterly."
        )

    data = MOCK_STOCK_DATA[symbol]
    name = data.get("name", symbol)
    price = data.get("price", 0.0)
    sector = data.get("sector", "n/a")
    market_cap = _humanize_number(data.get("market_cap"))
    pe_display = f"{data.get('pe_ratio'):.2f}" if data.get("pe_ratio") else "n/a"
    perf = get_performance_summary(symbol, "1mo")

    # Simple policy by risk level
    sizing = {"low": "1-3%", "medium": "3-6%", "high": "5-10%"}[risk]
    controls = {
        "short": "tight stops, catalyst-driven, reassess weekly",
        "medium": "trend/valuation checks, monthly review",
        "long-term": "DCA, fundamentals focus, quarterly review",
    }[horizon]
    tilt = {
        "low": "favor stability/dividends; avoid high volatility",
        "medium": "balance growth and stability",
        "high": "seek growth; accept higher volatility",
    }[risk]

    return (
        f"{name} ({symbol}) | Sector: {sector} | Price: ${price:.2f} | Cap: {market_cap} | P/E: {pe_display}\n"
        f"Recent: {perf}\n"
        f"- Risk profile: {risk}; Horizon: {horizon}\n"
        f"- Position size: {sizing} of portfolio\n"
        f"- Approach: {tilt}\n"
        f"- Controls: {controls}"
    )

@mcp.custom_route("/mcp/.well-known/oauth-protected-resource", methods=["GET"])
async def custom_well_known_endpoint(request: Request) -> Response:
  """OAuth protected resource metadata endpoint."""
  return JSONResponse({
      "resource": "http://localhost:8000/mcp",
      "authorization_servers": [ISSUER_URL],
      "scopes_supported": REQUIRED_SCOPES,
      "bearer_methods_supported": ["header"]
  })

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Stock Price MCP server")
  parser.add_argument("--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio")
  args = parser.parse_args()
  mcp.run(transport=args.transport)
