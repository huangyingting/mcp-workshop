# Copilot studio expects message endpoint returned in the Open SSE connection call must be a full URI.
# https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp#known-issues--planned-improvements
# Azure functions mcp extension does not support it yet, pending from preview.7
# https://github.com/Azure/azure-functions-mcp-extension/issues/40

import json
import math
import ast
import operator
from typing import Any, Callable, Dict  # added
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


class ToolProperty:
  def __init__(self, property_name: str, property_type: str, description: str):
    self.property_name = property_name
    self.property_type = property_type
    self.description = description

  def to_dict(self):
    return {
        "propertyName": self.property_name,
        "propertyType": self.property_type,
        "description": self.description,
    }


# Build operator and math whitelists once (module scope)
SUPPORTED_OPERATORS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,        # optional: allow modulus
    ast.FloorDiv: operator.floordiv,  # optional: allow floor division
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Split math symbols into constants vs callables to avoid returning function objects
_ALLOWED_MATH_ATTRS = {name: getattr(math, name) for name in dir(math) if not name.startswith("__")}
ALLOWED_MATH_CONSTS: Dict[str, float] = {
    k: v for k, v in _ALLOWED_MATH_ATTRS.items() if isinstance(v, (int, float))
}
ALLOWED_MATH_FUNCS: Dict[str, Callable[..., Any]] = {
    k: v for k, v in _ALLOWED_MATH_ATTRS.items() if callable(v)
}

# Simple safety limit to avoid pathological inputs
MAX_AST_NODES = 500

eval_tool_properties = [
    ToolProperty("expression", "string",
                 "The mathematical expression to evaluate."),
]

eval_tool_properties_json = json.dumps(
    [prop.to_dict() for prop in eval_tool_properties])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="evaluate",
    description="Evaluates a mathematical expression using the math module",
    toolProperties=eval_tool_properties_json,
)
def evaluate_math_expression(context: str) -> Any:
  """
  Evaluates a mathematical expression using Python's math module.
  Only allows numeric constants from math (e.g., pi) and callables (e.g., sin).
  """
  # Parse input payload
  try:
    content = json.loads(context)
  except Exception as e:
    return f"Invalid JSON: {e}"

  try:
    expression = content["arguments"]["expression"]
  except Exception:
    return "Missing required argument: arguments.expression"

  if not isinstance(expression, str):
    return "Expression must be a string"
  if not expression.strip():
    return "Expression must not be empty"

  def evaluate_ast_node(node: ast.AST) -> Any:
    # Numeric constants only
    if isinstance(node, ast.Constant):
      if isinstance(node.value, (int, float)):
        return node.value
      raise ValueError("Only numeric constants are allowed")

    # Allowed constants (e.g., pi, e, tau, inf, nan)
    if isinstance(node, ast.Name):
      if node.id in ALLOWED_MATH_CONSTS:
        return ALLOWED_MATH_CONSTS[node.id]
      raise ValueError(f"Unknown or disallowed name: {node.id}")

    # Binary operations
    if isinstance(node, ast.BinOp):
      op = SUPPORTED_OPERATORS.get(type(node.op))
      if op is None:
        raise ValueError("Unsupported binary operation")
      return op(evaluate_ast_node(node.left), evaluate_ast_node(node.right))

    # Unary operations (+x, -x)
    if isinstance(node, ast.UnaryOp):
      op = SUPPORTED_OPERATORS.get(type(node.op))
      if op is None:
        raise ValueError("Unsupported unary operation")
      return op(evaluate_ast_node(node.operand))

    # Function calls (e.g., sin(x))
    if isinstance(node, ast.Call):
      # Only simple names are allowed as functions
      if not isinstance(node.func, ast.Name):
        raise ValueError("Only direct calls to math functions are allowed")
      func_name = node.func.id
      func_obj = ALLOWED_MATH_FUNCS.get(func_name)
      if func_obj is None:
        raise ValueError(f"Unknown or disallowed function: {func_name}")
      args = [evaluate_ast_node(arg) for arg in node.args]
      # Disallow keywords for simplicity/safety
      if getattr(node, "keywords", []):
        raise ValueError("Keyword arguments are not allowed")
      return func_obj(*args)

    # Disallow everything else
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")

  try:
    # Parse and sanity-check the AST
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > MAX_AST_NODES:
      return "Expression too complex"

    # Evaluate safely
    return evaluate_ast_node(tree.body)
  except Exception as e:
    return str(e)
