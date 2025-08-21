"""
Run from repo root:
  uv run clients/console_client.py servers/simple_stock_server.py
  uv run clients/console_client.py http://localhost:8000/sse
  uv run clients/console_client.py http://localhost:8000/mcp
"""

import json, os, sys, logging
from collections.abc import Sequence
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from mcp import ClientSession, types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.context import RequestContext
from openai import AsyncAzureOpenAI

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("console_client")


def _to_oa_messages(msgs: list[types.SamplingMessage]) -> list[dict]:
  return [{"role": m.role, "content": getattr(m.content, "text", str(m.content))} for m in msgs]


class MCPClient:
  def __init__(self):
    self.exit_stack = AsyncExitStack()
    self.session: ClientSession | None = None
    self.available_tools: list[types.Tool] = []
    self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    self.azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    self.azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    self.azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    missing = [k for k, v in {
      "AZURE_OPENAI_ENDPOINT": self.azure_endpoint,
      "AZURE_OPENAI_API_KEY": self.azure_api_key,
      "AZURE_OPENAI_API_VERSION": self.azure_api_version,
      "AZURE_OPENAI_DEPLOYMENT": self.azure_deployment,
    }.items() if not v]
    if missing:
      raise RuntimeError(f"Missing Azure config: {', '.join(missing)}")
    self.openai = AsyncAzureOpenAI(
      azure_endpoint=self.azure_endpoint,
      api_key=self.azure_api_key,
      api_version=self.azure_api_version,
    )

  async def sampling_callback(
      self, _context: RequestContext[ClientSession, None], params: types.CreateMessageRequestParams
  ) -> types.CreateMessageResult:
    try:
      oa_msgs = _to_oa_messages(params.messages)
      last = oa_msgs[-1] if oa_msgs else {"role": None, "content": None}
      preview = last["content"]
      if isinstance(preview, str) and len(preview) > 160:
        preview = preview[:160] + "…"
      logger.info(
        "sampling_callback: model=%s msgs=%d last_role=%s last_preview=%r",
        self.azure_deployment, len(oa_msgs), last["role"], preview
      )

      r = await self.openai.chat.completions.create(
        model=self.azure_deployment,
        messages=oa_msgs,
      )
      return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text=r.choices[0].message.content or ""),
        model=self.azure_deployment,
        stopReason="endTurn",
      )
    except Exception as e:
      logger.error("sampling error: %s", e)
      return types.CreateMessageResult(
        content=types.TextContent(type="text", text=f"Sampling callback error: {e}"),
        model=self.azure_deployment,
        stopReason="endTurn",
      )

  async def elicitation_callback(self, *_):
    return types.ElicitResult(action="decline")

  async def _connect_with_streams(self, streams_ctx):
    read_stream, write_stream, *_ = await self.exit_stack.enter_async_context(streams_ctx)
    self.session = await self.exit_stack.enter_async_context(
      ClientSession(
        read_stream, write_stream,
        sampling_callback=self.sampling_callback,
        elicitation_callback=self.elicitation_callback,
      )
    )
    await self.session.initialize()
    self.available_tools = (await self.session.list_tools()).tools
    logger.info("Connected; tools: %s", [t.name for t in self.available_tools])

  async def connect(self, arg: str):
    if arg.endswith(".py"):
      await self._connect_with_streams(stdio_client(StdioServerParameters(command=sys.executable, args=[arg], env=None)))
      return
    if arg.startswith("http"):
      if arg.endswith("/sse"):
        await self._connect_with_streams(sse_client(url=arg)); return
      if arg.endswith("/mcp"):
        await self._connect_with_streams(streamablehttp_client(url=arg)); return
      raise ValueError("HTTP URL must end with '/sse' or '/mcp'")
    raise ValueError("Argument must be a .py file or an HTTP(S) URL")

  def _tool_specs(self) -> list[dict]:
    return [{
      "type": "function",
      "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema},
    } for t in self.available_tools]

  async def process_query(self, query: str) -> str:
    messages: list[dict] = [{"role": "user", "content": query}]
    tools = self._tool_specs()

    while True:
      resp = await self.openai.chat.completions.create(
        model=self.azure_deployment,
        messages=messages,
        tools=tools or None,
      )
      m = resp.choices[0].message
      if not m.tool_calls:
        return m.content or ""

      # Append assistant message with tool_calls as plain dicts
      messages.append({
        "role": "assistant",
        "tool_calls": [{
          "id": tc.id,
          "type": tc.type,
          "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        } for tc in m.tool_calls],
      })

      # Execute tool calls
      for tc in m.tool_calls:
        args = json.loads(tc.function.arguments or "{}")
        result = await self.session.call_tool(tc.function.name, args)
        payload = [c.model_dump() for c in result.content]
        logger.info("Tool %s(%s) -> %s", tc.function.name, args, payload)
        messages.append({
          "role": "tool",
          "tool_call_id": tc.id,
          "name": tc.function.name,
          "content": json.dumps(payload),
        })

  async def chat_loop(self) -> None:
    print("MCP Client Started! Type your queries or `quit` to exit.")
    while True:
      try:
        import readline
        q = input("Query: ").strip()
        if q.lower() in {"quit", "exit"}: break
        print(await self.process_query(q))
      except Exception as e:
        print(f"Error: {e!r}")

  async def cleanup(self):
    await self.exit_stack.aclose()


async def main(argv: Sequence[str]) -> None:
  if len(argv) < 2:
    print("Usage (connect):")
    print("  stdio:       uv run clients/console_client.py <server.py>")
    print("  HTTP (/mcp): uv run clients/console_client.py <url>/mcp")
    print("  SSE (/sse):  uv run clients/console_client.py <url>/sse")
    sys.exit(1)

  client = MCPClient()
  try:
    await client.connect(argv[1])
    await client.chat_loop()
  finally:
    await client.cleanup()


if __name__ == "__main__":
  import asyncio
  asyncio.run(main(sys.argv))