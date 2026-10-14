"""Optional Gemini fallback for complex Tableau expressions."""
from __future__ import annotations
import os
import re
from pydantic import BaseModel, Field

class GeminiConversion(BaseModel):
    dax: str = Field(description="The equivalent DAX expression only, without markdown fences.")
    explanation: str = Field(description="Brief explanation of the translation and semantic differences.")
    warnings: list[str] = Field(description="Assumptions, missing context, or semantic differences to review.")


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def convert_with_gemini(expression: str, table_name: str = "", calculated_field_name: str = "", model_context: str = "") -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("This expression needs AI assistance, but GEMINI_API_KEY is not configured. Add it to your .env file or simplify the expression.")

    # Import lazily so the app still runs without the Gemini package/key for local rules.
    from google import genai
    from google.genai import types

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)
    prompt = f"""You are an expert in Tableau calculated fields and Microsoft Power BI DAX.
Translate the Tableau expression into the closest semantically equivalent DAX expression.

Strict requirements:
- Preserve every existing table name, column name, field name, and business meaning exactly; do not invent or rename identifiers.
- If table context is provided, use it to qualify field references where appropriate.
- Do not claim equivalence if Tableau table calculations, LOD expressions, filter context, or data-model relationships cannot be inferred.
- Prefer valid DAX and use DIVIDE for division where a zero denominator is possible.
- Return only a structured response matching the schema. Put uncertainties and assumptions in warnings.
- Never add markdown fences to the dax property.

Calculated field name: {calculated_field_name or '(not provided)'}
Target table context: {table_name or '(not provided)'}
Power BI model context: {model_context or '(not provided)'}

Tableau expression:
{expression}
"""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiConversion,
            temperature=0.1,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response. Please retry or review the expression.")
    parsed = GeminiConversion.model_validate_json(response.text)
    dax = re.sub(r"^```(?:dax)?\s*|\s*```$", "", parsed.dax.strip(), flags=re.I)

    # Post-check identifiers: flag, never silently rewrite, missing source identifiers.
    source_fields = set(re.findall(r"\[([^\]]+)\]", expression))
    output_fields = set(re.findall(r"\[([^\]]+)\]", dax))
    missing = sorted(source_fields - output_fields)
    warnings = list(parsed.warnings)
    if missing:
        warnings.append("Review identifier preservation: these Tableau field references were not found verbatim in the DAX output: " + ", ".join(missing))
    if table_name and table_name.lower() not in dax.lower():
        warnings.append("The supplied table name does not appear in the output. Confirm whether DAX requires table qualification for these fields.")
    return {"dax": dax, "explanation": parsed.explanation, "warnings": warnings, "method": "gemini-fallback"}
