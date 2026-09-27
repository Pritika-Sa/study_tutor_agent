"""
unit_and_formula_tool -- the second required LangChain tool.

Chosen over a plain calculator (per the Phase 1 decision this project
flagged and the user confirmed) because a real capstone-scale need exists
on both tracks:

- NEET: unit conversion (SI/common units) and numeric formula evaluation
  for physics/chemistry problems (e.g. kinetic energy, molarity).
- Placement: the same formula evaluator covers aptitude arithmetic
  (percentages, permutations/combinations) and DSA complexity arithmetic
  (n*log2(n), factorial growth, etc.) -- there is no unit-conversion need
  on that side, so `evaluate_expression` is what Placement actually uses.

Expression evaluation is a hand-rolled, whitelisted AST walk -- never
Python's `eval()` -- so it can only ever perform arithmetic and a small set
of named math functions, nothing else.
"""
import ast
import math
import operator
from typing import Literal, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Safe expression evaluator
# ---------------------------------------------------------------------------

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARYOPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "comb": math.comb,     # nCr -- aptitude / DSA
    "perm": math.perm,     # nPr -- aptitude / DSA
    "factorial": math.factorial,
    "abs": abs,
    "round": round,
}


class UnsafeExpressionError(ValueError):
    pass


def _safe_eval(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, variables)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left, variables), _safe_eval(node.right, variables))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval(node.operand, variables))
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise UnsafeExpressionError(f"Unknown variable '{node.id}'")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_safe_eval(arg, variables) for arg in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise UnsafeExpressionError(f"Unsupported expression syntax: {ast.dump(node)}")


def evaluate_expression(expression: str, variables: Optional[dict[str, float]] = None) -> float:
    """Evaluates a whitelisted arithmetic expression (e.g. '0.5*m*v**2') against named variables. Never uses eval()."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Could not parse expression: {exc}") from exc
    return _safe_eval(tree, variables or {})


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

# (from_unit, to_unit) -> multiplier, for simple linear conversions.
_LINEAR_CONVERSIONS: dict[tuple[str, str], float] = {
    ("m", "cm"): 100, ("cm", "m"): 0.01,
    ("km", "m"): 1000, ("m", "km"): 0.001,
    ("mm", "m"): 0.001, ("m", "mm"): 1000,
    ("kg", "g"): 1000, ("g", "kg"): 0.001,
    ("mg", "g"): 0.001, ("g", "mg"): 1000,
    ("l", "ml"): 1000, ("ml", "l"): 0.001,
    ("hr", "min"): 60, ("min", "hr"): 1 / 60,
    ("min", "sec"): 60, ("sec", "min"): 1 / 60,
    ("hr", "sec"): 3600, ("sec", "hr"): 1 / 3600,
}


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    """Converts `value` between two units. Supports linear SI/common conversions plus Celsius<->Kelvin."""
    from_unit, to_unit = from_unit.strip().lower(), to_unit.strip().lower()
    if from_unit == to_unit:
        return value
    if (from_unit, to_unit) == ("celsius", "kelvin"):
        return value + 273.15
    if (from_unit, to_unit) == ("kelvin", "celsius"):
        return value - 273.15
    key = (from_unit, to_unit)
    if key not in _LINEAR_CONVERSIONS:
        raise UnsafeExpressionError(f"Unsupported unit conversion: '{from_unit}' -> '{to_unit}'")
    return value * _LINEAR_CONVERSIONS[key]


# ---------------------------------------------------------------------------
# LangChain tool
# ---------------------------------------------------------------------------

class UnitAndFormulaInput(BaseModel):
    operation: Literal["convert_unit", "evaluate_expression"] = Field(
        description="'convert_unit' for unit conversion, 'evaluate_expression' for a formula/arithmetic evaluation."
    )
    expression: Optional[str] = Field(
        default=None, description="Required for evaluate_expression, e.g. '0.5*m*v**2' or 'comb(10,3)'."
    )
    variables: Optional[dict[str, float]] = Field(
        default=None, description="Named variables used by `expression`, e.g. {'m': 2, 'v': 3}."
    )
    value: Optional[float] = Field(default=None, description="Required for convert_unit: the numeric value to convert.")
    from_unit: Optional[str] = Field(default=None, description="Required for convert_unit, e.g. 'km'.")
    to_unit: Optional[str] = Field(default=None, description="Required for convert_unit, e.g. 'm'.")

    @model_validator(mode="after")
    def _required_fields_present(self) -> "UnitAndFormulaInput":
        if self.operation == "evaluate_expression" and not self.expression:
            raise ValueError("expression is required when operation='evaluate_expression'")
        if self.operation == "convert_unit" and (self.value is None or not self.from_unit or not self.to_unit):
            raise ValueError("value, from_unit, and to_unit are required when operation='convert_unit'")
        return self


@tool("unit_and_formula_tool", args_schema=UnitAndFormulaInput)
def unit_and_formula_tool(
    operation: Literal["convert_unit", "evaluate_expression"],
    expression: Optional[str] = None,
    variables: Optional[dict[str, float]] = None,
    value: Optional[float] = None,
    from_unit: Optional[str] = None,
    to_unit: Optional[str] = None,
) -> dict:
    """
    Educational numeric utility for both tracks. NEET: unit conversion and
    physics/chemistry formula evaluation (e.g. kinetic energy, molarity).
    Placement: the same formula evaluator covers aptitude arithmetic
    (percentages, nCr/nPr) and DSA complexity arithmetic (n*log2(n), etc.).
    Never uses eval() -- only a whitelisted set of operators/functions.
    """
    if operation == "convert_unit":
        result = convert_unit(value, from_unit, to_unit)
        return {"operation": operation, "value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result}

    result = evaluate_expression(expression, variables)
    return {"operation": operation, "expression": expression, "variables": variables or {}, "result": result}
