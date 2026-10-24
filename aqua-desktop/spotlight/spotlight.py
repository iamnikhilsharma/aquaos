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


CURRENCY_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 152.0,
    "INR": 84.0,
    "CAD": 1.38,
    "AUD": 1.52,
    "CHF": 0.88,
    "CNY": 7.24,
}

CURRENCY_SYMBOLS: Dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
}

UNIT_FACTORS: Dict[str, Tuple[str, float]] = {
    # Data Storage (base: bytes)
    "b": ("data", 1.0 / 8),
    "bit": ("data", 1.0 / 8),
    "bits": ("data", 1.0 / 8),
    "byte": ("data", 1.0),
    "bytes": ("data", 1.0),
    "kb": ("data", 1024.0),
    "kib": ("data", 1024.0),
    "mb": ("data", 1024.0 ** 2),
    "mib": ("data", 1024.0 ** 2),
    "gb": ("data", 1024.0 ** 3),
    "gib": ("data", 1024.0 ** 3),
    "tb": ("data", 1024.0 ** 4),
    "tib": ("data", 1024.0 ** 4),
    "pb": ("data", 1024.0 ** 5),
    # Length (base: meters)
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "m": ("length", 1.0),
    "meter": ("length", 1.0),
    "meters": ("length", 1.0),
    "km": ("length", 1000.0),
    "kilometer": ("length", 1000.0),
    "kilometers": ("length", 1000.0),
    "in": ("length", 0.0254),
    "inch": ("length", 0.0254),
    "inches": ("length", 0.0254),
    "ft": ("length", 0.3048),
    "feet": ("length", 0.3048),
    "foot": ("length", 0.3048),
    "yd": ("length", 0.9144),
    "yard": ("length", 0.9144),
    "yards": ("length", 0.9144),
    "mi": ("length", 1609.344),
    "mile": ("length", 1609.344),
    "miles": ("length", 1609.344),
    # Mass / Weight (base: grams)
    "mg": ("mass", 0.001),
    "g": ("mass", 1.0),
    "gram": ("mass", 1.0),
    "grams": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "kilogram": ("mass", 1000.0),
    "kilograms": ("mass", 1000.0),
    "oz": ("mass", 28.3495),
    "ounce": ("mass", 28.3495),
    "ounces": ("mass", 28.3495),
    "lb": ("mass", 453.592),
    "lbs": ("mass", 453.592),
    "pound": ("mass", 453.592),
    "pounds": ("mass", 453.592),
    # Time (base: seconds)
    "s": ("time", 1.0),
    "sec": ("time", 1.0),
    "second": ("time", 1.0),
    "seconds": ("time", 1.0),
    "min": ("time", 60.0),
    "mins": ("time", 60.0),
    "minute": ("time", 60.0),
    "minutes": ("time", 60.0),
    "h": ("time", 3600.0),
    "hr": ("time", 3600.0),
    "hrs": ("time", 3600.0),
    "hour": ("time", 3600.0),
    "hours": ("time", 3600.0),
    "day": ("time", 86400.0),
    "days": ("time", 86400.0),
}


def evaluate_conversion(expr: str) -> Optional[Dict[str, str]]:
    """Convert currency, digital storage, temperature, distance, or weight expressions."""
    import re

    cleaned = expr.strip()
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z°$€£¥₹]+)\s+(?:to|in)\s+([a-zA-Z°$€£¥₹]+)$", cleaned, re.IGNORECASE)
    if not match:
        return None

    val_str, u1_raw, u2_raw = match.groups()
    try:
        val = float(val_str)
    except ValueError:
        return None

    u1 = CURRENCY_SYMBOLS.get(u1_raw, u1_raw.upper())
    u2 = CURRENCY_SYMBOLS.get(u2_raw, u2_raw.upper())

    # 1. Currency Conversion
    if u1 in CURRENCY_RATES and u2 in CURRENCY_RATES:
        rate_u1 = CURRENCY_RATES[u1]
        rate_u2 = CURRENCY_RATES[u2]
        converted = (val / rate_u1) * rate_u2
        res_str = f"{converted:,.2f} {u2}"
        return {
            "title": f"{val:g} {u1} = {res_str}",
            "subtitle": f"Spotlight Currency Conversion (1 {u1} ≈ {rate_u2 / rate_u1:.4g} {u2}) — Press Enter to copy",
            "action_cmd": f"copy:{res_str}",
        }

    # 2. Temperature Conversion
    temp_units = {"C": "celsius", "CELSIUS": "celsius", "F": "fahrenheit", "FAHRENHEIT": "fahrenheit", "K": "kelvin", "KELVIN": "kelvin"}
    t1 = temp_units.get(u1.replace("°", ""))
    t2 = temp_units.get(u2.replace("°", ""))
    if t1 and t2:
        # Convert t1 to Celsius
        c_val = val if t1 == "celsius" else (val - 32) * 5 / 9 if t1 == "fahrenheit" else val - 273.15
        if t2 == "celsius":
            out_val = c_val
            out_sym = "°C"
        elif t2 == "fahrenheit":
            out_val = (c_val * 9 / 5) + 32
            out_sym = "°F"
        else:
            out_val = c_val + 273.15
            out_sym = "K"
        res_str = f"{round(out_val, 2):g} {out_sym}"
        return {
            "title": f"{val:g}° {u1} = {res_str}",
            "subtitle": "Spotlight Temperature Conversion — Press Enter to copy",
            "action_cmd": f"copy:{res_str}",
        }

    # 3. Physical & Data Unit Conversion
    u1_low = u1.lower()
    u2_low = u2.lower()
    if u1_low in UNIT_FACTORS and u2_low in UNIT_FACTORS:
        cat1, f1 = UNIT_FACTORS[u1_low]
        cat2, f2 = UNIT_FACTORS[u2_low]
        if cat1 == cat2:
            base_val = val * f1
            out_val = base_val / f2
            formatted = f"{out_val:,.4f}".rstrip("0").rstrip(".") if "." in f"{out_val:,.4f}" else f"{out_val:,.0f}"
            res_str = f"{formatted} {u2_raw}"
            return {
                "title": f"{val:g} {u1_raw} = {res_str}",
                "subtitle": f"Spotlight {cat1.capitalize()} Conversion — Press Enter to copy",
                "action_cmd": f"copy:{res_str}",
            }

    return None


@dataclass
class SpotlightResult:
    """Single item returned by a Spotlight query."""

    category: str  # "CALCULATOR" | "AI" | "APPLICATION" | "SYSTEM_COMMAND" | "REA" | "FILE"
    title: str
    subtitle: str
    action_cmd: str
    icon: str = "system-search"


class SpotlightEngine:
    """Processes Spotlight queries across math, conversions, AI, applications, and REA inspection."""

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
        q_low = q.lower()

        # 1. Check unit & currency conversions (e.g., "16 GB to MB", "100 USD to EUR", "72 F to C")
        conv_res = evaluate_conversion(q)
        if conv_res is not None:
            results.append(
                SpotlightResult(
                    category="CALCULATOR",
                    title=conv_res["title"],
                    subtitle=conv_res["subtitle"],
                    action_cmd=conv_res["action_cmd"],
                    icon="accessories-calculator",
                )
            )

        # 2. Check inline calculator
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

        # 3. Direct REA Reverse Engineering Queries (e.g. `rea python`, `inspect /usr/bin/bash`, `dissect ./target.exe`)
        if q_low.startswith("rea ") or q_low.startswith("inspect ") or q_low.startswith("dissect "):
            parts = q.split(None, 1)
            target = parts[1].strip() if len(parts) > 1 else "/usr/bin/python3"
            results.append(
                SpotlightResult(
                    category="REA",
                    title=f"🔬 Deep Inspect '{target}' with REA",
                    subtitle="Reverse engineer PE/ELF headers, sections, 32-chunk Shannon entropy & security mitigations",
                    action_cmd=f"rea:{target}",
                    icon="security-high",
                )
            )

        # 4. Check explicit @ai / ? prefix or OS natural language intent
        if q_low.startswith("@ai ") or q.startswith("?"):
            ai_prompt = q[4:].strip() if q_low.startswith("@ai ") else q[1:].strip()
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

        # 5. Fast System Actions & Toggles
        sys_actions_map = [
            ("dark mode", "Toggle Dark / Light Mode", "Switch between Sonoma dark and light glass appearance", "sys:dark"),
            ("light mode", "Toggle Dark / Light Mode", "Switch between Sonoma dark and light glass appearance", "sys:dark"),
            ("lock screen", "Lock Screen", "Secure session with glass lock screen (Ctrl+L)", "sys:lock"),
            ("lock", "Lock Screen", "Secure session with glass lock screen (Ctrl+L)", "sys:lock"),
            ("terminal", "GNU Bash Terminal", "Open interactive bash shell environment (/bin/bash)", "sys:terminal"),
            ("bash", "GNU Bash Terminal", "Open interactive bash shell environment (/bin/bash)", "sys:terminal"),
            ("finder", "Finder", "Explore Linux RootFS, workspace and host files", "sys:finder"),
            ("ai studio", "Aqua AI Studio", "Local LLM code generation and sandboxed Python runner", "sys:ai"),
            ("shield", "Aqua Shield & REA", "Gatekeeper Zero-Trust and Reverse Engineer Anything suite", "sys:shield"),
            ("gatekeeper", "Aqua Shield & REA", "Binary verification, SHA-256 integrity and entropy scanner", "sys:shield"),
            ("activity monitor", "Activity Monitor", "Real-time process viewer, CPU, memory and cgroup sandboxes", "sys:activity"),
            ("settings", "System Settings", "Configure Displays, Sound, Dock, Privacy and Appearance", "sys:settings"),
            ("empty trash", "Empty Trash", "Clean local discarded files from ~/.local/share/Trash", "sys:trash"),
            ("pytest", "Run Automated Tests", "Execute all 16 AquaOS test suites in bash terminal", "sys:tests"),
            ("tests", "Run Automated Tests", "Execute all 16 AquaOS test suites in bash terminal", "sys:tests"),
        ]
        for trigger, title, sub, cmd in sys_actions_map:
            if trigger in q_low or q_low in trigger:
                results.append(
                    SpotlightResult(
                        category="SYSTEM_COMMAND",
                        title=title,
                        subtitle=sub,
                        action_cmd=cmd,
                        icon="preferences-system",
                    )
                )

        # 6. Fuzzy search applications
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

        # 7. Check if target is a binary path or library for REA analysis
        if any(q_low.endswith(ext) for ext in [".exe", ".dll", ".so", ".bin", ".elf", ".appimage", ".py"]) or q.startswith("/usr/bin/") or q.startswith("/bin/"):
            if not any(r.category == "REA" for r in results):
                results.append(
                    SpotlightResult(
                        category="REA",
                        title=f"🔬 Deep Inspect '{q}' with REA",
                        subtitle="Reverse engineer PE/ELF headers, sections, 32-chunk Shannon entropy & security mitigations",
                        action_cmd=f"rea:{q}",
                        icon="security-high",
                    )
                )

        # 8. Always offer a fallback "Ask Aqua Intelligence" item
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
