"""Local-first Tableau-to-DAX conversion rules.

This is intentionally conservative: unsupported/context-sensitive expressions are
routed to the optional Gemini fallback rather than being presented as certain.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict

@dataclass
class Conversion:
    dax: str
    method: str
    needs_ai: bool
    warnings: list[str]
    explanation: str

    def to_dict(self):
        return asdict(self)

# Patterns whose semantics usually require model context or specialized translation.
COMPLEX_MARKERS = (
    "{FIXED", "{INCLUDE", "{EXCLUDE", "RUNNING_SUM", "RUNNING_AVG", "WINDOW_SUM",
    "WINDOW_AVG", "LOOKUP(", "PREVIOUS_VALUE(", "INDEX(", "RANK(", "RANK_UNIQUE(",
    "FIRST(", "LAST(", "SIZE(", "DATETRUNC(", "DATEPART(", "MAKEDATE(", "CASE ",
    "REGEXP_", "SCRIPT_", "MODEL_", "ATTR(", "TOTAL(", "PERCENTILE(", "MEDIAN(",
)

FUNC_MAP = {
    "SUM": "SUM", "AVG": "AVERAGE", "MIN": "MIN", "MAX": "MAX",
    "COUNT": "COUNT", "COUNTD": "DISTINCTCOUNT", "ABS": "ABS",
    "ROUND": "ROUND", "SQRT": "SQRT", "POWER": "POWER",
    "LEN": "LEN", "LEFT": "LEFT", "RIGHT": "RIGHT", "UPPER": "UPPER",
    "LOWER": "LOWER", "TRIM": "TRIM", "CONTAINS": "CONTAINSSTRING",
    "ISNULL": "ISBLANK", "IFNULL": "COALESCE", "ZN": "COALESCE",
}


def _has_complex_marker(expr: str) -> bool:
    upper = expr.upper()
    return any(marker in upper for marker in COMPLEX_MARKERS) or bool(re.search(r"\{\s*(FIXED|INCLUDE|EXCLUDE)\b", upper)) or bool(re.search(r"\bELSEIF\b", upper))


def _qualify_fields(expr: str, table_name: str) -> str:
    if not table_name.strip():
        return expr
    # Tableau field references are bracketed. Do not qualify known function-like tokens.
    escaped_table = table_name.replace("'", "''")
    return re.sub(r"\[([^\[\]]+)\]", lambda m: f"'{escaped_table}'[{m.group(1)}]", expr)


def _replace_function_calls(expr: str) -> str:
    # Handle ZN separately: Tableau ZN(x) means return zero when x is null.
    expr = re.sub(r"\bZN\s*\(([^()]*)\)", r"COALESCE(\1, 0)", expr, flags=re.IGNORECASE)
    # Function replacement only; nested arguments remain intact.
    for tableau, dax in sorted(FUNC_MAP.items(), key=lambda x: -len(x[0])):
        expr = re.sub(rf"\b{tableau}\s*\(", f"{dax}(", expr, flags=re.IGNORECASE)
    # Tableau IFNULL(x,y) and ZN(x) need DAX's COALESCE signature.
    # ZN(x) is equivalent to COALESCE(x, 0), not COALESCE(x).
    expr = re.sub(r"\bCOALESCE\(([^(),]+)\)", r"COALESCE(\1, 0)", expr, flags=re.IGNORECASE) if re.search(r"\bZN\s*\(", expr, re.I) else expr
    # Tableau IIF(condition, true, false) -> DAX IF(condition, true, false)
    expr = re.sub(r"\bIIF\s*\(", "IF(", expr, flags=re.IGNORECASE)
    # Tableau != is accepted in DAX, normalize Tableau equality operator.
    expr = expr.replace("<> ", "<> ")
    # Tableau string concatenation uses +, also valid in DAX for strings in many contexts.
    return expr


def convert_locally(expression: str, table_name: str = "", calculated_field_name: str = "") -> Conversion:
    source = expression.strip()
    if not source:
        raise ValueError("Enter a Tableau expression before converting.")
    if _has_complex_marker(source):
        return Conversion(source, "local-review", True,
                          ["This expression may depend on Tableau LOD, table-calculation, or context-specific behavior."],
                          "The expression was identified as context-sensitive and should be handled by the AI fallback or reviewed manually.")

    # Convert IF / ELSEIF / END only when the shape is simple enough to do safely.
    if re.search(r"\bELSEIF\b", source, re.I):
        return Conversion(source, "local-review", True,
                          ["Nested Tableau conditional syntax needs a structured conversion."],
                          "A conditional construct needs deeper parsing before a safe DAX translation can be produced.")

    result = source
    # Tableau boolean operators are valid in DAX; normalize for readability.
    result = re.sub(r"\bAND\b", "&&", result, flags=re.I)
    result = re.sub(r"\bOR\b", "||", result, flags=re.I)
    result = re.sub(r"\bNOT\s+", "NOT ", result, flags=re.I)
    result = re.sub(r"\bIIF\s*\(", "IF(", result, flags=re.I)
    result = _replace_function_calls(result)

    # Basic Tableau IF ... THEN ... ELSE ... END conversion.
    simple_if = re.fullmatch(r"\s*IF\s+(.+?)\s+THEN\s+(.+?)\s+ELSE\s+(.+?)\s+END\s*", result, re.I | re.S)
    if simple_if:
        result = f"IF({simple_if.group(1).strip()}, {simple_if.group(2).strip()}, {simple_if.group(3).strip()})"
    elif re.search(r"\bTHEN\b", result, re.I):
        return Conversion(source, "local-review", True,
                          ["The conditional expression is not in the supported simple IF/THEN/ELSE form."],
                          "The expression requires structured conditional parsing.")

    # Field qualification is done last so names inside the translated expression are preserved.
    result = _qualify_fields(result, table_name)
    warnings = []
    if not table_name.strip() and re.search(r"\[[^\]]+\]", result):
        warnings.append("No table name was supplied. Field references were preserved but may need table qualification in DAX.")
    if re.search(r"\b(AVG|COUNTD|IFNULL|ZN|IIF)\s*\(", source, re.I):
        explanation = "Translated supported Tableau functions to their DAX equivalents. Review the output against your data model."
    else:
        explanation = "Converted using local rules; no Gemini API call was needed. Review the output in your Power BI model."
    return Conversion(result, "local-rules", False, warnings, explanation)
