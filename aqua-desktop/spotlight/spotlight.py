"""AquaOS Spotlight Search, Calculator & Inline AI (spotlight.py).

Bound to Super+Space / Alt+Space. Provides:
1. Safe AST Math & Scientific Expression Calculator (e.g., `24 * 365`, `sqrt(256) + 18`, `hex(255)`)
2. Inline Apple Intelligence-style AI Queries (prefix with `@ai`, `?`, or natural language questions)
3. Instant Fuzzy Application & Universal Bundle Search (.desktop, .app, .AppImage, .exe)
4. Fast System & Security Quick Commands (`dark mode`, `neural boost`, `scan`, `lock`)
"""

from __future__ import annotations

import ast
import math
import operator
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.ai_engine import AquaAIEngine
from core.app_indexer import AppIndexer
from core.config import AquaConfig


SAFE_OPERATORS: Dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "abs": abs,
    "round": round,
    "hex": hex,
    "bin": bin,
    "pi": lambda: math.pi,
    "e": lambda: math.e,
}


def evaluate_math_expression(expr: str) -> Optional[str]:
    """Safely evaluate a mathematical expression using Python's AST without eval()."""
    cleaned = expr.strip().replace("^", "**")
    if not cleaned or len(cleaned) > 120:
        return None

    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError:
        return None

    def _eval_node(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "pi":
                return math.pi
            if node.id == "e":
                return math.e
            raise ValueError(f"Unknown identifier: {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            return SAFE_OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
            return SAFE_OPERATORS[type(node.op)](_eval_node(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn_name = node.func.id
            if fn_name in SAFE_FUNCTIONS:
                args = [_eval_node(arg) for arg in node.args]
                return SAFE_FUNCTIONS[fn_name](*args)
        raise ValueError("Unsupported AST expression")

    try:
        val = _eval_node(tree)
        if isinstance(val, float):
            if val.is_integer():
                return str(int(val))
            return str(round(val, 8))
        return str(val)
    except Exception:
        return None


@dataclass
class SpotlightResult:
    """Single item returned by a Spotlight query."""

    category: str  # "CALCULATOR" | "AI" | "APPLICATION" | "SYSTEM_COMMAND"
    title: str
    subtitle: str
    action_cmd: str
    icon: str = "system-search"


class SpotlightEngine:
    """Processes Spotlight queries across math, AI, applications, and OS actions."""

    def __init__(
        self,
        indexer: Optional[AppIndexer] = None,
        ai_engine: Optional[AquaAIEngine] = None,
        config: Optional[AquaConfig] = None,
    ) -> None:
        self.config = config or AquaConfig()
        self.indexer = indexer or AppIndexer()
        self.ai_engine = ai_engine or AquaAIEngine()

    def query(self, text: str) -> List[SpotlightResult]:
        q = text.strip()
        if not q:
            return []

        results: List[SpotlightResult] = []

        # 1. Check inline calculator
        math_res = evaluate_math_expression(q)
        if math_res is not None:
            results.append(
                SpotlightResult(
                    category="CALCULATOR",
                    title=f"{q} = {math_res}",
                    subtitle="Spotlight Scientific Calculator — Press Enter to copy result",
                    action_cmd=f"copy:{math_res}",
                    icon="accessories-calculator",
                )
            )

        # 2. Check explicit @ai / ? prefix or OS natural language intent
        if q.lower().startswith("@ai ") or q.startswith("?"):
            ai_prompt = q[4:].strip() if q.lower().startswith("@ai ") else q[1:].strip()
            ai_reply = self.ai_engine.ask(ai_prompt)
            results.append(
                SpotlightResult(
                    category="AI",
                    title=f"✦ Aqua Intelligence ({ai_reply['tokens_per_sec']} tok/s)",
                    subtitle=ai_reply["response"],
                    action_cmd="python3 -m ai.ai_studio",
                    icon="applications-science",
                )
            )
            return results

        os_intent = self.ai_engine.parse_os_intent(q)
        if os_intent is not None:
            results.append(
                SpotlightResult(
                    category="SYSTEM_COMMAND",
                    title=os_intent["message"],
                    subtitle=f"AquaOS System Action ({os_intent['action']})",
                    action_cmd=f"intent:{os_intent['action']}",
                    icon="preferences-system",
                )
            )

        # 3. Fuzzy search applications
        for app in self.indexer.search(q, limit=6):
            badge = " [Sandboxed]" if app.sandboxed else ""
            results.append(
                SpotlightResult(
                    category="APPLICATION",
                    title=f"{app.name}{badge}",
                    subtitle=app.comment or app.exec_cmd,
                    action_cmd=app.exec_cmd,
                    icon=app.icon,
                )
            )

        # 4. Always offer a fallback "Ask Aqua Intelligence" item
        results.append(
            SpotlightResult(
                category="AI",
                title=f"Ask Aqua Intelligence: \"{q}\"",
                subtitle="Query local DeepSeek-R1 / Qwen 2.5 LLM with Neural Boost",
                action_cmd=f"ai:{q}",
                icon="applications-science",
            )
        )
        return results


def main() -> None:
    engine = SpotlightEngine()
    query_str = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "sqrt(256) * 12"
    for item in engine.query(query_str):
        print(f"[{item.category}] {item.title} — {item.subtitle}")


if __name__ == "__main__":
    main()
