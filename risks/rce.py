"""
Run from the risks directory:
    uv run rce.py -t streamable-http
"""

from mcp.server.fastmcp import FastMCP
import argparse
import math
import ast
import operator
from typing import Union, Iterable

mcp = FastMCP("rce")


def _is_number(x) -> bool:
  # Reject bools (subclass of int) and accept int/float only
  return (isinstance(x, (int, float)) and not isinstance(x, bool))


def _assert_number(x, ctx: str = "value"):
  if not _is_number(x):
    raise ValueError(f"{ctx} must be a number")


def _safe_factorial(n: int) -> int:
  if not isinstance(n, int) or isinstance(n, bool) or n < 0:
    raise ValueError("factorial expects a non-negative integer")
  if n > 200:
    raise ValueError("factorial input too large (max 200)")
  return math.factorial(n)


def _safe_comb(n: int, k: int) -> int:
  for name, v in (("n", n), ("k", k)):
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
      raise ValueError(f"comb expects non-negative integers; bad {name}={v!r}")
  if n > 200 or k > 200:
    raise ValueError("comb inputs too large (max 200)")
  return math.comb(n, k)


def _safe_perm(n: int, k: int = None) -> int:
  if not isinstance(n, int) or isinstance(n, bool) or n < 0:
    raise ValueError("perm expects non-negative integers")
  if k is not None and (not isinstance(k, int) or isinstance(k, bool) or k < 0):
    raise ValueError("perm expects non-negative integers")
  if n > 200 or (k is not None and k > 200):
    raise ValueError("perm inputs too large (max 200)")
  return math.perm(n, k) if k is not None else math.perm(n)


def _safe_pow(a: float, b: float):
  _assert_number(a, "base")
  _assert_number(b, "exponent")

  # Bound exponentiation to avoid DoS / huge integers
  # If exponent is an integer, cap |b|; if fractional exponent, cap |a|
  if float(b).is_integer():
    if abs(b) > 10:
      raise ValueError("exponent too large (max |10|)")
    if abs(a) > 1_000_000:
      raise ValueError("base too large (max |1e6|)")
  else:
    if abs(a) > 1_000_000:
      raise ValueError("base too large for fractional exponent (max |1e6|)")

  result = operator.pow(a, b)
  # A soft sanity check on magnitude
  if _is_number(result) and abs(result) > 1e308:
    raise ValueError("result too large")
  return result


# Define allowed operators
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _safe_pow,
}
_UNARY_OPS = {
    ast.USub: operator.neg,
    # ast.UAdd could be allowed if desired:
    # ast.UAdd: operator.pos,
}

# Allowed math constants as bare names
_SAFE_CONSTANTS = {k: getattr(math, k) for k in ("pi", "e", "tau", "inf", "nan") if hasattr(math, k)}

# Allowed math functions (whitelist)
_SAFE_FUNCS = {
    # Trig and hyperbolic
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "asinh": math.asinh, "acosh": math.acosh, "atanh": math.atanh,
    # Exponentials and logs
    "exp": math.exp, "log": math.log, "log10": math.log10, "log2": math.log2,
    "sqrt": math.sqrt,
    # Rounding and misc
    "fabs": math.fabs, "floor": math.floor, "ceil": math.ceil, "trunc": math.trunc,
    "fmod": math.fmod, "remainder": math.remainder, "hypot": math.hypot,
    "degrees": math.degrees, "radians": math.radians, "copysign": math.copysign,
    # Special functions
    "erf": math.erf, "erfc": math.erfc, "gamma": math.gamma, "lgamma": math.lgamma,
    # Bounded heavy hitters
    "pow": _safe_pow, "factorial": _safe_factorial, "comb": _safe_comb, "perm": _safe_perm,
    # Predicates (return bools; still safe)
    "isfinite": math.isfinite, "isinf": math.isinf, "isnan": math.isnan,
}


def _count_nodes(node: ast.AST) -> int:
  return 1 + sum(_count_nodes(child) for child in ast.iter_child_nodes(node))


def _eval_node(node: ast.AST, depth: int = 0):
  if depth > 50:
    raise ValueError("expression too deep")

  # Number constant (reject non-numeric constants)
  if isinstance(node, ast.Constant):
    if _is_number(node.value):
      return node.value
    raise ValueError(f"unsupported constant type: {type(node.value).__name__}")

  # Variable/function name (allow constants only)
  if isinstance(node, ast.Name):
    if node.id in _SAFE_CONSTANTS:
      return _SAFE_CONSTANTS[node.id]
    raise ValueError(f"unknown name: {node.id}")

  # Binary operations
  if isinstance(node, ast.BinOp):
    op_type = type(node.op)
    if op_type not in _BIN_OPS:
      raise ValueError("unsupported binary operation")
    left = _eval_node(node.left, depth + 1)
    right = _eval_node(node.right, depth + 1)
    _assert_number(left, "left operand")
    _assert_number(right, "right operand")
    return _BIN_OPS[op_type](left, right)

  # Unary operations
  if isinstance(node, ast.UnaryOp):
    op_type = type(node.op)
    if op_type not in _UNARY_OPS:
      raise ValueError("unsupported unary operation")
    operand = _eval_node(node.operand, depth + 1)
    _assert_number(operand, "operand")
    return _UNARY_OPS[op_type](operand)

  # Function calls (like sin(x))
  if isinstance(node, ast.Call):
    if node.keywords:
      raise ValueError("keyword arguments are not supported")
    if not isinstance(node.func, ast.Name):
      raise ValueError("complex function calls are not supported")
    func_name = node.func.id
    func = _SAFE_FUNCS.get(func_name)
    if func is None:
      raise ValueError(f"unknown or disallowed function: {func_name}")
    args = [_eval_node(arg, depth + 1) for arg in node.args]
    for i, a in enumerate(args):
      # Allow bool outputs from predicates like isfinite, but ensure inputs are numeric
      if func not in (math.isfinite, math.isinf, math.isnan):
        _assert_number(a, f"argument {i+1}")
    return func(*args)

  # Parentheses, etc., are handled implicitly by AST; no extra case needed.

  raise ValueError(f"unsupported expression node: {type(node).__name__}")


@mcp.tool()
def calculate(expression: str) -> Union[float, int, str]:
  """
  Safely evaluates a mathematical expression.

  Allowed:
    - Numbers, parentheses, +, -, *, /, ** (bounded)
    - Math constants: pi, e, tau, inf, nan
    - Whitelisted math functions (e.g., sin, cos, sqrt, log, exp, …)
  Limits:
    - Expression length <= 256 characters
    - AST nodes <= 128
    - Max recursion depth (50)
    - Bounded exponentiation and combinatorics
  Returns:
    - Number on success, or error message string on failure.
  """
  try:
    if not isinstance(expression, str):
      return "expression must be a string"
    if len(expression) > 256:
      return "expression too long (max 256 characters)"

    # Parse the expression into an AST
    tree = ast.parse(expression, mode='eval')

    # Basic structural limits
    if _count_nodes(tree) > 128:
      return "expression too complex"

    # Evaluate the AST safely
    result = _eval_node(tree.body)

    # Ensure we only return serializable basic numerics/bools
    if _is_number(result) or isinstance(result, bool):
      return result
    return "unexpected non-numeric result"
  except Exception as e:
    return str(e)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="RCE")
  parser.add_argument(
      "--transport", "-t", choices=["stdio", "sse", "streamable-http"], default="stdio")
  args = parser.parse_args()
  mcp.run(transport=args.transport)