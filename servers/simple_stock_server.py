"""
Run from the repository root:
    uv run mcp run simple_stock_server.py -t streamable-http, or
    uv run mcp dev simple_stock_server.py, or
    uv run simple_stock_server.py -t streamable-http
"""

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession
from mcp.types import SamplingMessage, TextContent
from mcp.server.fastmcp.prompts import base
import argparse
import logging
from pydantic import BaseModel, Field
import pandas as pd
from datetime import datetime, timedelta
import random

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

mcp = FastMCP("stock_server")

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

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Stock Price MCP server")
  parser.add_argument("--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio")
  args = parser.parse_args()
  mcp.run(transport=args.transport)
