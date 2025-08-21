"""
Run from the repository root:
    uv run mcp run servers/stock_server.py -t streamable-http, or
    uv run mcp dev servers/stock_server.py, or
    uv run servers/stock_server.py -t streamable-http
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

# Mock stock data
MOCK_STOCK_DATA = {
    "AAPL": {"price": 175.50, "name": "Apple Inc.", "sector": "Technology", "market_cap": 2800000000000, "pe_ratio": 28.5, "dividend_yield": 0.0048},
    "MSFT": {"price": 509.77, "name": "Microsoft Corporation", "sector": "Technology", "market_cap": 3790000000000, "pe_ratio": 37.32, "dividend_yield": 0.65},
    "GOOGL": {"price": 138.25, "name": "Alphabet Inc.", "sector": "Technology", "market_cap": 1750000000000, "pe_ratio": 24.8, "dividend_yield": 0.0},
    "AMZN": {"price": 145.80, "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "market_cap": 1520000000000, "pe_ratio": 42.1, "dividend_yield": 0.0},
    "TSLA": {"price": 215.99, "name": "Tesla Inc.", "sector": "Consumer Discretionary", "market_cap": 687000000000, "pe_ratio": 58.3, "dividend_yield": 0.0},
    "META": {"price": 325.45, "name": "Meta Platforms Inc.", "sector": "Technology", "market_cap": 850000000000, "pe_ratio": 23.7, "dividend_yield": 0.0035},
    "NVDA": {"price": 445.32, "name": "NVIDIA Corporation", "sector": "Technology", "market_cap": 1100000000000, "pe_ratio": 65.2, "dividend_yield": 0.0012}
}


def generate_mock_historical_data(symbol: str, period: str = "1mo") -> pd.DataFrame:
  """Generate mock historical data for a given symbol and period."""
  if symbol not in MOCK_STOCK_DATA:
    return pd.DataFrame()

  base_price = MOCK_STOCK_DATA[symbol]["price"]

  # Determine number of days based on period
  if period == "1mo":
    days = 30
  elif period == "3mo":
    days = 90
  elif period == "1y":
    days = 365
  elif period == "1d":
    days = 1
  else:
    days = 30

  # Generate dates
  end_date = datetime.now()
  dates = [end_date - timedelta(days=i) for i in range(days, 0, -1)]

  # Generate price data with some volatility
  prices = []
  current_price = base_price * 0.95  # Start slightly lower

  for _ in dates:
    # Add some random volatility (±2%)
    change = random.uniform(-0.02, 0.02)
    current_price *= (1 + change)
    prices.append(current_price)

  # Make sure the last price matches our "current" price
  prices[-1] = base_price

  # Create DataFrame
  data = pd.DataFrame({
      "Open": [p * random.uniform(0.99, 1.01) for p in prices],
      "High": [p * random.uniform(1.005, 1.03) for p in prices],
      "Low": [p * random.uniform(0.97, 0.995) for p in prices],
      "Close": prices,
      "Volume": [random.randint(50000000, 200000000) for _ in prices]
  }, index=dates)

  return data


mcp = FastMCP("stock_server")


def get_performance_summary(symbol: str, period: str) -> str:
  """
  Build a concise performance summary string for a stock over the given period.
  Shared by prompts and sampling tools to avoid duplicated logic.
  """
  try:
    data = generate_mock_historical_data(symbol, period)
    if data.empty:
      last = get_stock_price(symbol)
      if last >= 0:
        return f"No recent history for {symbol} over {period}. Latest known price ${last:.2f}."
      return f"No recent history and no current price available for {symbol}."
    first_close = float(data["Close"].iloc[0])
    last_close = float(data["Close"].iloc[-1])
    change = last_close - first_close
    pct = (change / first_close) * 100 if first_close else 0.0
    return f"{symbol} {change:+.2f} ({pct:+.2f}%) over {period}. Latest close ${last_close:.2f}."
  except Exception as e:
    return f"Error gathering data for {symbol}: {e}"


@mcp.resource("stock://{symbol}")
def stock_resource(symbol: str) -> str:
  """
  Expose stock price data as a resource.
  Returns a formatted string with the current stock price for the given symbol.
  """
  price = get_stock_price(symbol)
  if price < 0:
    return f"Error: Could not retrieve price for symbol '{symbol}'."
  return f"The current price of '{symbol}' is ${price:.2f}."


@mcp.resource("stock://tickers")
def tickers_resource() -> str:
  """
  Return a list of stock tickers.
  """
  return "AAPL, MSFT, GOOGL, AMZN, TSLA, META, NVDA"


@mcp.prompt("stock_analysis_prompt")
def stock_analysis(symbol: str, period: str = "1mo"):
  """
  Build a prompt for analyzing a stock's recent performance.
  Returns a list of MCP prompt messages for clients to use directly.
  """
  summary = get_performance_summary(symbol, period)
  return [
      base.UserMessage(
          f"You are a concise financial analysis assistant. Provide a short analysis of {symbol}. Context: {summary} Discuss trend, momentum, and any notable risk.")
  ]


@mcp.tool()
def get_stock_price(symbol: str) -> float:
  """
  Retrieve the current stock price for the given ticker symbol.
  Returns the latest closing price as a float.
  """
  try:
    if symbol in MOCK_STOCK_DATA:
      return float(MOCK_STOCK_DATA[symbol]["price"])
    else:
      return -1.0
  except Exception:
    return -1.0


@mcp.tool()
def get_stock_history(symbol: str, period: str = "1mo") -> str:
  """
  Retrieve historical data for a stock given a ticker symbol and a period.
  Returns the historical data as a CSV formatted string.

  Parameters:
      symbol: The stock ticker symbol.
      period: The period over which to retrieve historical data (e.g., '1mo', '3mo', '1y').
  """
  try:
    data = generate_mock_historical_data(symbol, period)
    if data.empty:
      return f"No historical data found for symbol '{symbol}' with period '{period}'."
    return data.to_csv()
  except Exception as e:
    return f"Error fetching historical data: {str(e)}"


@mcp.tool()
def compare_stock_prices(symbol1: str, symbol2: str) -> str:
  """
  Compare the current stock prices of two ticker symbols.
  Returns a formatted message comparing the two stock prices.

  Parameters:
      symbol1: The first stock ticker symbol.
      symbol2: The second stock ticker symbol.
  """
  price1 = get_stock_price(symbol1)
  price2 = get_stock_price(symbol2)
  if price1 < 0 or price2 < 0:
    return f"Error: Could not retrieve data for comparison of '{symbol1}' and '{symbol2}'."
  if price1 > price2:
    result = f"{symbol1} (${price1:.2f}) is higher than {symbol2} (${price2:.2f})."
  elif price1 < price2:
    result = f"{symbol1} (${price1:.2f}) is lower than {symbol2} (${price2:.2f})."
  else:
    result = f"Both {symbol1} and {symbol2} have the same price (${price1:.2f})."
  return result


@mcp.tool()
async def stock_headline_sampling(symbol: str, ctx: Context[ServerSession, None]) -> str:
  """
  Use MCP sampling to generate a very short market-style headline for the given stock.
  Combines recent performance context with the client's model to produce one headline.
  """
  context = get_performance_summary(symbol, "1mo")
  text = f"""Create a stock headline based on the following data
{context}
"""  
  result = await ctx.session.create_message(
      messages=[
          SamplingMessage(
              role="user",
              content=TextContent(type="text", text=text),
          )
      ],
      max_tokens=100,
  )
  if result.content.type == "text":
    return result.content.text
  return str(result.content)


def _humanize_number(n: float | int | None) -> str:
  """Human-friendly formatter for big numbers (e.g., 1.23T, 456.7B, 12.3M)."""
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

  include_week_range: bool = Field(
      default=False,
      description="Whether to include 52-week high/low information",
  )


@mcp.tool()
async def get_ticker_info(
    symbol: str,
    ctx: Context[ServerSession, None],
) -> str:
  """
  Get key information for a ticker symbol with optional 52-week range data.
  """
  # Ask user if they want 52-week range info
  result = await ctx.elicit(
      message="Would you like to include 52-week high/low information?",
      schema=WeekRangePreference,
  )
  include_week_range = (
      result.action == "accept"
      and result.data
      and result.data.include_week_range
  )

  try:
    if symbol not in MOCK_STOCK_DATA:
      return f"No information available for '{symbol}'"

    stock_data = MOCK_STOCK_DATA[symbol]

    # Extract basic info from mock data
    name = stock_data["name"]
    price = stock_data["price"]
    currency = "USD"
    market_cap = _humanize_number(stock_data["market_cap"])
    pe_ratio = stock_data["pe_ratio"]
    pe_display = f"{pe_ratio:.2f}" if pe_ratio else "n/a"
    dividend_yield = stock_data["dividend_yield"] * 100
    sector = stock_data["sector"]

    # Build result string
    result = f"""{name} ({symbol})
Price: ${price:.2f} {currency}
Market Cap: {market_cap}
PE Ratio: {pe_display}
Dividend Yield: {dividend_yield:.2f}%
Sector: {sector}"""

    # Add 52-week range if requested
    if include_week_range:
      # Generate mock 52-week range based on current price
      week_low = price * 0.75  # 25% below current
      week_high = price * 1.25  # 25% above current
      result += f"\n52W Range: ${week_low:.2f} - ${week_high:.2f}"

    return result

  except Exception as e:
    return f"Error fetching info for '{symbol}': {e}"


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Stock Price MCP server")
  parser.add_argument("--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio",
                      help='Transport protocol to use ("stdio", "sse", or "streamable-http")')
  args = parser.parse_args()
  mcp.run(transport=args.transport)
