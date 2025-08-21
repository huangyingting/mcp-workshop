# MCP Workshop

## Table of Contents
1. [Introduction to MCP](#introduction-to-mcp)
2. [Core MCP Concepts](#core-mcp-concepts)
3. [Workshop Setup](#workshop-setup)
4. [Demo 1: Basic Stock Server](#demo-1-basic-stock-server)
5. [Demo 2: OAuth-Protected Weather Server](#demo-2-oauth-protected-weather-server)
6. [Hands-on Exercises](#hands-on-exercises)
7. [Advanced Topics](#advanced-topics)
8. [Resources](#resources)

## Introduction to MCP

The **Model Context Protocol (MCP)** is an open standard that enables AI assistants to securely connect to data sources and tools. Think of it as a universal API that allows language models to interact with external systems in a standardized way.

### Why MCP?
- **Standardization**: One protocol for all integrations
- **Security**: Built-in authentication and authorization
- **Flexibility**: Supports multiple transport methods
- **Extensibility**: Easy to add new capabilities

## Core MCP Concepts

### 1. Resources
Resources are read-only data sources that can be accessed by AI models. They represent information that the model can read but not modify.

**Example from our stock server:**
```python
@mcp.resource("stock://{symbol}")
def stock_resource(symbol: str) -> str:
    """Expose stock price data as a resource."""
    price = get_stock_price(symbol)
    return f"The current price of '{symbol}' is ${price:.2f}."
```

### 2. Tools
Tools are functions that AI models can call to perform actions or retrieve dynamic data. Unlike resources, tools can have side effects.

**Example from our stock server:**
```python
@mcp.tool()
def get_stock_price(symbol: str) -> float:
    """Retrieve the current stock price for the given ticker symbol."""
    # Tool implementation
```

### 3. Prompts
Prompts are reusable templates that help structure interactions with AI models. They provide context and formatting for specific use cases.

**Example from our stock server:**
```python
@mcp.prompt("stock_analysis_prompt")
def stock_analysis(symbol: str, period: str = "1mo"):
    """Build a prompt for analyzing a stock's recent performance."""
    # Returns formatted prompt messages
```

### 4. Sampling
Sampling allows MCP servers to request completions from the connected AI model, enabling interactive and context-aware responses.

**Example from our stock server:**
```python
@mcp.tool()
async def stock_headline_sampling(symbol: str, ctx: Context[ServerSession, None]) -> str:
    """Use MCP sampling to generate a market-style headline."""
    # Uses the client's model to generate content
```

### 5. Authentication & Authorization
MCP supports OAuth 2.0 for secure access to protected resources, ensuring that only authorized users can access sensitive data.

## Workshop Setup

### Prerequisites
- Python 3.8+
- uv (Python package manager)

### Installation
```bash
# Clone this repository
git clone <repository-url>
cd mcp-workshop

# Install dependencies
uv sync
```

## Demo 1: Basic Stock Server

Our first demo showcases a comprehensive MCP server that provides stock market data through various MCP primitives.

### Key Features Demonstrated

#### 1. Multiple Resources
```python
@mcp.resource("stock://{symbol}")  # Individual stock data
@mcp.resource("stock://tickers")   # List of available tickers
```

#### 2. Various Tool Types
- **Simple data retrieval**: `get_stock_price()`
- **Historical data**: `get_stock_history()`
- **Comparison logic**: `compare_stock_prices()`
- **Interactive tools**: `get_ticker_info()` with user elicitation

#### 3. Prompts for AI Interaction
The `stock_analysis_prompt` demonstrates how to create structured prompts for AI analysis.

#### 4. Advanced Features
- **Sampling**: Generate headlines using the client's AI model
- **User Elicitation**: Ask users for preferences during tool execution
- **Mock Data Generation**: Realistic stock data simulation

### Running the Stock Server

```bash
# Run with stdio transport (for desktop clients)
uv run servers/stock_server.py

# Run with HTTP transport (for web clients)
uv run servers/stock_server.py -t streamable-http

# Development mode with auto-reload
uv run mcp dev servers/stock_server.py
```

### Testing the Stock Server

1. **Resource Access**: Try accessing `stock://AAPL` or `stock://tickers`
2. **Tool Calls**: Use `get_stock_price("AAPL")` or `compare_stock_prices("AAPL", "MSFT")`
3. **Prompts**: Invoke the `stock_analysis_prompt` for AAPL
4. **Interactive Tools**: Use `get_ticker_info()` and see the elicitation in action

## Demo 2: OAuth-Protected Weather Server

Our second demo shows how to implement OAuth 2.0 authentication with Azure Entra ID, demonstrating enterprise-grade security.

### Security Features

#### 1. JWT Token Verification
```python
class EntraIdTokenVerifier(TokenVerifier):
    """JWT token verifier for Entra ID (Azure AD)."""
    async def verify_token(self, token: str) -> AccessToken | None:
        # Verifies JWT signatures, expiration, audience, and issuer
```

#### 2. Scope-Based Authorization
The server requires specific scopes to access weather data:
```python
REQUIRED_SCOPES = [f"api://{CLIENT_ID}/{SCOPE}" for SCOPE in SCOPES.split(",")]
```

#### 3. RFC 9728 Compliance
Implements the OAuth 2.0 Protected Resource Metadata standard:
```python
@mcp.custom_route("/mcp/.well-known/oauth-protected-resource", methods=["GET"])
async def custom_well_known_endpoint(request: Request) -> Response:
    # Returns metadata about the protected resource
```

### Setting Up OAuth

1. **Environment Configuration**:
   Create a `.env` file:
   ```
   TENANT_ID=your-azure-tenant-id
   CLIENT_ID=your-azure-app-client-id
   SCOPES=weather.read,weather.write
   ```

2. **Azure App Registration**:
   - Register an application in Azure Entra ID
   - Configure API permissions and scopes
   - Note the Tenant ID and Client ID

### Running the OAuth Server

```bash
# Ensure .env file is configured
uv run servers/oauth_weather_server.py
```

The server will:
- Start on `http://localhost:8000/mcp`
- Serve the `.well-known/oauth-protected-resource` endpoint
- Require valid JWT tokens for weather data access

## Hands-on Exercises

### Exercise 1: Extend the Stock Server
Add a new tool that calculates portfolio value:

```python
@mcp.tool()
def calculate_portfolio_value(holdings: dict[str, int]) -> str:
    """
    Calculate total portfolio value.
    holdings: dict mapping stock symbols to share counts
    """
    # Your implementation here
    pass
```

### Exercise 2: Add a New Resource
Create a resource that provides market sector information:

```python
@mcp.resource("stock://sectors")
def sectors_resource() -> str:
    """Return available market sectors."""
    # Your implementation here
    pass
```

### Exercise 3: Create a Custom Prompt
Design a prompt for risk assessment:

```python
@mcp.prompt("risk_assessment_prompt")
def risk_assessment(symbol: str, risk_tolerance: str):
    """Generate a risk assessment prompt."""
    # Your implementation here
    pass
```

### Exercise 4: Implement User Elicitation
Create a tool that asks users for their investment preferences:

```python
class InvestmentPreference(BaseModel):
    risk_level: str = Field(description="low, medium, or high")
    time_horizon: str = Field(description="short, medium, or long-term")

@mcp.tool()
async def get_investment_advice(symbol: str, ctx: Context[ServerSession, None]) -> str:
    """Provide investment advice based on user preferences."""
    # Use ctx.elicit() to get user preferences
    pass
```

## Advanced Topics

### Transport Protocols
MCP supports multiple transport methods:
- **stdio**: For desktop applications
- **SSE (Server-Sent Events)**: For web applications
- **HTTP**: For REST-like interactions

### Error Handling
Best practices for robust MCP servers:
```python
@mcp.tool()
def robust_tool(param: str) -> str:
    try:
        # Tool logic
        return result
    except SpecificException as e:
        return f"Specific error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return "An unexpected error occurred"
```

### Performance Optimization
- Cache frequently accessed data
- Use async/await for I/O operations
- Implement connection pooling for external APIs

### Security Best Practices
- Always validate input parameters
- Use HTTPS in production
- Implement rate limiting
- Log security events
- Regularly rotate secrets

## Key Takeaways

1. **MCP provides a standardized way** to connect AI models to external data and tools
2. **Resources, Tools, and Prompts** are the core primitives for different interaction patterns
3. **OAuth 2.0 integration** enables enterprise-grade security
4. **FastMCP** simplifies server development with decorators and automatic schema generation
5. **Multiple transport protocols** support various deployment scenarios

## Resources

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Python SDK Documentation](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP Guide](https://github.com/modelcontextprotocol/python-sdk/tree/main/src/mcp/server/fastmcp)
- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)
- [Protected Resource Metadata RFC 9728](https://tools.ietf.org/html/rfc9728)

## Next Steps

1. **Build your own MCP server** for your domain
2. **Integrate with existing APIs** and databases
3. **Implement authentication** for sensitive data
4. **Deploy to production** with proper monitoring
5. **Contribute to the MCP ecosystem** with open-source servers

---

*This workshop provides hands-on experience with MCP development. For production deployments, ensure proper security reviews and testing.*