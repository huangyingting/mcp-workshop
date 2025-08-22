# MCP Workshop

## Table of Contents
1. [Introduction to MCP](#introduction-to-mcp)
2. [Core MCP Concepts](#core-mcp-concepts)
3. [Workshop Setup](#workshop-setup)
4. [Console Client](#console-client)
5. [EntraID Client](#entraid-client)
6. [Demo 1: Basic Stock Server](#demo-1-basic-stock-server)
7. [Demo 2: OAuth-Protected Weather Server](#demo-2-oauth-protected-weather-server)
8. [Hands-on Exercises](#hands-on-exercises)
9. [Advanced Topics](#advanced-topics)
10. [Resources](#resources)

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
- Python 3.11+
- uv (Python package manager)
- Azure OpenAI service (for the console client)

### Installation
```bash
# Clone this repository
git clone <repository-url>
cd mcp-workshop

# Install dependencies
uv sync
```

### Azure OpenAI Configuration
Create a `.env` file in the `clients` directory for Azure OpenAI integration (used by clients/console_client.py):

```bash
# Azure OpenAI Configuration (required for console client)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
```

### OAuth Configuration
Create a `.env` file in the `servers` diretory for authorization (used by servers/entraid_weather_server.py and clients/entraid_client.py):
```bash
# OAuth Configuration (for weather server demo)
TENANT_ID=your-azure-tenant-id
CLIENT_ID=your-azure-app-client-id
SCOPES=MCP.Tools,MCP.Resources,MCP.Prompts
```

## Console Client

The workshop includes a comprehensive console client (`clients/console_client.py`) that demonstrates how to build MCP clients.

```mermaid
graph TB
    subgraph "Initialization"
        Start([Start]) --> ParseArgs[Parse Command Line Arguments]
        ParseArgs --> CheckArg{Check Argument Type}
        CheckArg -->|.py file| ConnectStdio[Connect to STDIO Server]
        CheckArg -->|http://.../sse| ConnectSSE[Connect to SSE Server]
        CheckArg -->|http://.../mcp| ConnectHTTP[Connect to HTTP Server]
        
        ConnectStdio --> InitSession[Initialize Client Session]
        ConnectSSE --> InitSession
        ConnectHTTP --> InitSession
        
        InitSession --> ListTools[List Available Tools]
        ListTools --> ChatLoop[Start Chat Loop]
    end
    
    subgraph "Chat Loop"
        ChatLoop --> UserInput[Get User Input]
        UserInput --> CheckQuit{Quit?}
        CheckQuit -->|Yes| Cleanup[Cleanup & Exit]
        CheckQuit -->|No| ProcessQuery[Process Query]
    end
    
    subgraph "Query Processing"
        ProcessQuery --> PrepareMessages[Prepare Messages Array]
        PrepareMessages --> PrepareTools[Format Available Tools]
        PrepareTools --> CallOpenAI[Call Azure OpenAI API]
        
        CallOpenAI --> CheckToolCalls{Has Tool Calls?}
        CheckToolCalls -->|No| ReturnResponse[Return Response]
        CheckToolCalls -->|Yes| AddAssistantMsg[Add Assistant Message]
        
        AddAssistantMsg --> ProcessToolCalls[Process Tool Calls]
        ProcessToolCalls --> CallMCPTool[Call MCP Tool via Session]
        CallMCPTool --> AddToolResponse[Add Tool Response to Messages]
        AddToolResponse --> CallOpenAI
    end
    
    subgraph "MCP Session Components"
        Session[ClientSession]
        Session --> SamplingCB[Sampling Callback]
        Session --> ElicitationCB[Elicitation Callback]
        SamplingCB --> AzureOpenAI2[Azure OpenAI]
        ElicitationCB --> Decline[Always Decline]
    end
    
    ReturnResponse --> DisplayResult[Display Result]
    DisplayResult --> UserInput
    
    subgraph "Transport Layers"
        StdioTransport[STDIO Transport<br/>Python subprocess]
        SSETransport[SSE Transport<br/>Server-Sent Events]
        HTTPTransport[HTTP Transport<br/>Streamable HTTP]
    end
    
    ConnectStdio -.-> StdioTransport
    ConnectSSE -.-> SSETransport
    ConnectHTTP -.-> HTTPTransport
    
    style Start fill:#90EE90
    style Cleanup fill:#FFB6C1
    style CallOpenAI fill:#87CEEB
    style CallMCPTool fill:#DDA0DD
```

### Key Features

#### 1. Multi-Transport Support
The client supports all MCP transport protocols:
- **stdio**: For local Python servers
- **HTTP**: For streamable HTTP MCP servers
- **Server-Sent Events (SSE)**: For SSE MCP servers

#### 2. Azure OpenAI Integration
- Uses Azure OpenAI for chat completions
- Implements MCP sampling callbacks
- Supports function calling with MCP tools
- Handles tool execution and response formatting

#### 3. Interactive Chat Loop
- Provides a readline-enabled console interface
- Automatically discovers and uses available MCP tools
- Handles tool calls and responses seamlessly

### Running the Console Client

#### With stdio Transport (Local Servers)
```bash
# Connect to the stock server
uv run clients/console_client.py servers/simple_stock_server.py

# Connect to the weather server
uv run clients/entraid_client.py servers/entraid_weather_server.py
```

#### With HTTP Transport
```bash
# Connect to HTTP/MCP endpoint
uv run clients/console_client.py http://localhost:8000/mcp

# Connect to SSE endpoint  
uv run clients/console_client.py http://localhost:8000/sse
```

### Example Usage Session

```
$ uv run clients/console_client.py servers/simple_stock_server.py
MCP Client Started! Type your queries or `quit` to exit.

Query: What's the current price of Apple stock?
Tool get_stock_price({'symbol': 'AAPL'}) -> [{'type': 'text', 'text': 'The current price of AAPL is $150.25'}]
The current price of Apple stock (AAPL) is $150.25.

Query: Compare Apple and Microsoft stock prices
Tool compare_stock_prices({'symbol1': 'AAPL', 'symbol2': 'MSFT'}) -> [{'type': 'text', 'text': 'AAPL ($150.25) vs MSFT ($380.50): MSFT is 153.2% higher than AAPL'}]
Comparing Apple (AAPL) and Microsoft (MSFT):
- AAPL: $150.25
- MSFT: $380.50
Microsoft's stock is currently 153.2% higher than Apple's.

Query: quit
```

### Client Architecture

#### Sampling Callback
The client implements MCP sampling to allow servers to use the AI model:
```python
async def sampling_callback(self, context, params):
    # Converts MCP messages to OpenAI format
    # Calls Azure OpenAI chat completion
    # Returns formatted MCP response
```

#### Tool Execution Flow
1. User query is sent to Azure OpenAI with available MCP tools
2. If tools are called, the client executes them via MCP
3. Tool results are sent back to Azure OpenAI
4. Final response is presented to the user

## EntraID Client
The workshop also includes an EntraID client (`clients/entraid_client.py`) that demonstrates how to implement OAuth 2.0 authentication with Entra ID.

```mermaid
sequenceDiagram
    participant User
    participant Client as "MCP Client"
    participant MCPServer as "MCP Server"
    participant EntraID as "Microsoft Entra ID"

    User->>+Client: Run script

    Note over Client: Creates EntraIDDeviceCodeAuth instance
    Client->>MCPServer: Initial API Request (no auth token)
    MCPServer-->>Client: 401 Unauthorized with WWW-Authenticate header

    Client->>Client: Discover protected resource metadata URL from header
    alt Metadata URL not in header
        Client->>MCPServer: GET /.well-known/oauth-protected-resource
        MCPServer-->>Client: Return resource metadata (auth server, scopes)
    else Metadata URL present
        Client->>MCPServer: GET metadata from URL
        MCPServer-->>Client: Return resource metadata (auth server, scopes)
    end

    Note over Client: Initializes MSAL PublicClientApplication
    Client->>EntraID: Initiate Device Code Flow
    EntraID-->>Client: Device Code & User Verification URL

    Client->>User: Display verification URL and code
    User->>EntraID: Authenticates in browser
    
    Client->>EntraID: Poll for token with device code
    EntraID-->>Client: Access Token

    Note over Client: Store token and prepare authed request
    Client->>MCPServer: Retry API Request with Bearer Token
    MCPServer-->>Client: 200 OK

    Note over Client: Establish MCP Session
    Client->>MCPServer: MCP Handshake (Initialize)
    MCPServer-->>Client: MCP Handshake (Ack)

    Client->>MCPServer: list_tools()
    MCPServer-->>Client: Tools list

    Client->>MCPServer: list_resources()
    MCPServer-->>Client: Resources list

    Client->>-User: Print available tools and resources
```

### What it does
- Implements httpx.Auth to handle OAuth for MCP over Streamable HTTP.
- Discovers OAuth metadata (RFC 9728) from WWW-Authenticate or falls back to `/.well-known/oauth-protected-resource`.
- Parses ProtectedResourceMetadata to auto-configure scopes and authorization server.
- Uses MSAL device code flow with silent token acquisition and in-memory cache.
- Retries the original request after obtaining a token and then lists tools and resources.

### Prerequisites
- Server running at http://localhost:8000/mcp (entraid_weather_server.py).
- Environment variable for the client app registration:
  - CLIENT_ID=your-azure-app-client-id

Example .env (in `clients` directory):
```
CLIENT_ID=00000000-0000-0000-0000-000000000000
```

### How it works (flow)
1. Send request without a token; receive 401.
2. Discover protected resource metadata:
   - Prefer resource_metadata from WWW-Authenticate.
   - Fallback to `/.well-known/oauth-protected-resource` at the server origin.
3. Parse scopes and authorization_servers from metadata.
4. Initialize MSAL PublicClientApplication with discovered authority.
5. Try silent token; if absent/expired, start device code flow (prints a code and URL).
6. Apply Bearer token and retry the original MCP request.

### Run
```bash
# Terminal 1: start the OAuth-protected server
uv run servers/entraid_weather_server.py

# Terminal 2: run the Entra ID client
uv run clients/entraid_client.py
```

### Sample output
```
To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code ABCD-EFGH to authenticate.
Available tools: ['get_weather']
Available resources: []
```

## Demo 1: Basic Stock Server

Our first demo showcases a comprehensive MCP server that provides stock market data through various MCP primitives.

```mermaid
graph TB
    %% Main Server
    Server[FastMCP Stock Server<br/>simple_stock_server.py]
    
    %% Mock Data Store
    MockData[(MOCK_STOCK_DATA<br/>AAPL, MSFT, GOOGL<br/>AMZN, TSLA, META, NVDA)]
    
    %% Resources
    subgraph Resources["📊 MCP Resources"]
        StockResource["stock://{symbol}<br/>Current Price Data"]
        TickersResource["stock://tickers<br/>Available Tickers List"]
    end
    
    %% Tools
    subgraph Tools["🔧 MCP Tools"]
        GetPrice["get_stock_price(symbol)<br/>→ float"]
        GetHistory["get_stock_history(symbol, period)<br/>→ CSV string"]
        CompareStocks["compare_stock_prices(symbol1, symbol2)<br/>→ comparison string"]
        GetTickerInfo["get_ticker_info(symbol)<br/>→ comprehensive info"]
        HeadlineSampling["stock_headline_sampling(symbol)<br/>→ AI-generated headline"]
    end
    
    %% Prompts
    subgraph Prompts["💬 MCP Prompts"]
        StockAnalysis["stock_analysis_prompt(symbol, period)<br/>→ Analysis prompt for AI"]
    end
    
    %% Helper Functions
    subgraph Helpers["⚙️ Helper Functions"]
        GenHistorical["generate_mock_historical_data()<br/>→ pandas DataFrame"]
        GetPerformance["get_performance_summary()<br/>→ performance string"]
        HumanizeNumber["_humanize_number()<br/>→ formatted numbers"]
    end
    
    %% Schemas
    subgraph Schemas["📋 Pydantic Schemas"]
        WeekRangeSchema["WeekRangePreference<br/>include_week_range: bool"]
    end
    
    %% External Interactions
    Client[MCP Client]
    AIModel[AI Model<br/>for sampling]
    
    %% Main connections
    Client -->|MCP Protocol| Server
    Server --> Resources
    Server --> Tools
    Server --> Prompts
    
    %% Data flow
    MockData --> GetPrice
    MockData --> GetHistory
    MockData --> CompareStocks
    MockData --> GetTickerInfo
    MockData --> StockResource
    MockData --> TickersResource
    
    %% Tool dependencies
    GetHistory --> GenHistorical
    GetTickerInfo --> HumanizeNumber
    GetTickerInfo --> WeekRangeSchema
    StockAnalysis --> GetPerformance
    GetPerformance --> GenHistorical
    HeadlineSampling -->|sampling request| AIModel
    
    %% Resource dependencies
    StockResource --> GetPrice
    
    %% Styling
    classDef serverClass fill:#e1f5fe,stroke:#0277bd,stroke-width:3px
    classDef dataClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef toolClass fill:#e8f5e8,stroke:#388e3c,stroke-width:2px
    classDef resourceClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef promptClass fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    classDef helperClass fill:#f1f8e9,stroke:#689f38,stroke-width:2px
    classDef schemaClass fill:#e0f2f1,stroke:#00695c,stroke-width:2px
    classDef externalClass fill:#ffebee,stroke:#d32f2f,stroke-width:2px
    
    class Server serverClass
    class MockData dataClass
    class GetPrice,GetHistory,CompareStocks,GetTickerInfo,HeadlineSampling toolClass
    class StockResource,TickersResource resourceClass
    class StockAnalysis promptClass
    class GenHistorical,GetPerformance,HumanizeNumber helperClass
    class WeekRangeSchema schemaClass
    class Client,AIModel externalClass
```

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
# Run with stdio transport (for console client)
uv run servers/simple_stock_server.py

# Run with HTTP transport (for web clients)
uv run servers/simple_stock_server.py -t streamable-http

# Development mode with auto-reload
uv run mcp dev servers/simple_stock_server.py
```

### Testing the Stock Server
#### Using the Console Client
```bash
# Start the console client with the stock server
uv run clients/console_client.py servers/simple_stock_server.py

# Try these example queries:
# - "What's the price of Tesla stock?"
# - "Compare Apple and Google stock prices"  
# - "Show me the stock analysis prompt for Microsoft"
# - "Generate a headline for Amazon stock"
```

#### Direct Testing
```bash
uv run mcp dev servers/simple_stock_server.py
```
1. **Resource Access**: Try accessing `stock://AAPL` or `stock://tickers`
2. **Tool Calls**: Use `get_stock_price("AAPL")` or `compare_stock_prices("AAPL", "MSFT")`
3. **Prompts**: Invoke the `stock_analysis_prompt` for AAPL
4. **Interactive Tools**: Use `get_ticker_info()` and see the elicitation in action

## Demo 2: OAuth-Protected Weather Server

Our second demo shows how to implement OAuth 2.0 authentication with Azure Entra ID, demonstrating enterprise-grade security.

```mermaid
graph TB
    %% External Systems
    Client[Client Application]
    EntraID[Microsoft Entra ID<br/>OAuth Provider]
    
    %% Main Application Components
    subgraph "OAuth Weather Server"
        direction TB
        
        %% FastMCP Framework
        FastMCP[FastMCP Server<br/>HTTP Transport]
        AuthSettings[Auth Settings<br/>- Issuer URL<br/>- Resource Server URL<br/>- Required Scopes]
        
        %% Token Verification
        EntraIdTokenVerifier[EntraIdTokenVerifier<br/>- Tenant ID<br/>- Client ID<br/>- JWKS Cache]
        JWKS[JWKS Cache<br/>1-hour TTL]
        
        %% Business Logic
        WeatherTool[get_weather Tool<br/>Random Weather Data]
        WellKnown[OAuth Metadata<br/>/.well-known/oauth-protected-resource]
        
        %% Configuration
        Config[Environment Config<br/>- TENANT_ID<br/>- CLIENT_ID<br/>- SCOPES]
    end
    
    %% External JWKS Endpoint
    JWKSEndpoint[JWKS Endpoint<br/>login.microsoftonline.com]
    
    %% Flow Connections
    Client -->|Request with Bearer Token| FastMCP
    FastMCP -->|Verify Token| EntraIdTokenVerifier
    EntraIdTokenVerifier -->|Check Cache| JWKS
    EntraIdTokenVerifier -->|Fetch if Expired| JWKSEndpoint
    JWKSEndpoint -->|Return Keys| JWKS
    
    EntraIdTokenVerifier -->|JWT Verification| EntraID
    EntraID -->|Validate Signature| EntraIdTokenVerifier
    
    FastMCP -->|Authorized Request| WeatherTool
    WeatherTool -->|Weather Data| FastMCP
    FastMCP -->|Response| Client
    
    %% OAuth Discovery
    Client -->|OAuth Discovery| WellKnown
    WellKnown -->|Metadata| Client
    
    %% Configuration
    Config -.->|Configure| AuthSettings
    Config -.->|Configure| EntraIdTokenVerifier
    
    %% Styling
    classDef external fill:#e1f5fe
    classDef server fill:#f3e5f5
    classDef auth fill:#fff3e0
    classDef tool fill:#e8f5e8
    classDef config fill:#fce4ec
    
    class Client,EntraID,JWKSEndpoint external
    class FastMCP server
    class EntraIdTokenVerifier,AuthSettings,JWKS auth
    class WeatherTool,WellKnown tool
    class Config config
```

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

### Setting Up Authorization

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

### Running the Server with Authorization Support
```bash
# Ensure .env file is configured with Azure settings
uv run servers/entraid_weather_server.py
```

The server will:
- Start on `http://localhost:8000/mcp`
- Serve the `.well-known/oauth-protected-resource` endpoint
- Require valid JWT tokens for weather data access

#### Testing with CLI (Device Code)
```bash
# Start the OAuth-protected server in one terminal
uv run servers/entraid_weather_server.py

# In another terminal, authenticate and connect using the Entra ID client
uv run clients/entraid_client.py
```

#### Testing with VSCode
1. Open `.vscode/mcp.json` and click `Start` above the `entraid_weather_server` entry to connect to the MCP server
2. VSCode will automatically handle OAuth token acquisition and authentication
3. In Copilot Chat, switch to `Agent` mode and select `MCP Server: entraid_weather_server`
4. Interact with the server using natural language queries, such as "What is the weather like in Seattle?"

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
6. **Azure OpenAI integration** enables powerful AI-driven interactions with MCP servers
7. **Console clients** provide an excellent testing and development environment

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