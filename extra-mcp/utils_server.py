import ast
import operator
import os
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

PORT = int(os.environ.get("PORT", "8000"))
mcp = FastMCP("utils", host="0.0.0.0", port=PORT)

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

GLOSSARY = {
    "mcp": "Model Context Protocol, a standard way for AI clients to call tools.",
    "gateway": "One endpoint that routes tool calls to many MCP servers.",
    "ingress": "A Kubernetes object that exposes a service through a hostname.",
    "helm": "The package manager used to deploy this project to Kubernetes.",
}


def evaluate(node):
    """Evaluates only numbers and + - * / ** so no arbitrary code can run."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = evaluate(node.left), evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](evaluate(node.operand))
    raise ValueError("unsupported expression")


@mcp.tool()
def current_time() -> dict:
    """Return the current UTC date and time."""
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@mcp.tool()
def calculate(expression: str) -> dict:
    """Evaluate a math expression such as '(12 + 8) * 3'."""
    tree = ast.parse(expression, mode="eval")
    return {"expression": expression, "result": evaluate(tree.body)}


@mcp.tool()
def search(query: str) -> list:
    """Search a small built-in glossary of project terms."""
    q = query.lower()
    return [
        {"term": k, "meaning": v}
        for k, v in GLOSSARY.items()
        if q in k or q in v.lower()
    ]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
