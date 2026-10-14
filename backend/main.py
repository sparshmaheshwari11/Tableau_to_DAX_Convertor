from __future__ import annotations
import io
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.converter import convert_locally
from backend.gemini_service import convert_with_gemini, gemini_configured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
app = FastAPI(title="Tableau to DAX Converter", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "frontend")), name="static")

class ConvertRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=12000)
    table_name: str = ""
    calculated_field_name: str = ""
    model_context: str = ""
    use_ai: bool = True

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE_DIR / "frontend" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"status": "ok", "gemini_configured": gemini_configured(), "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash")}

@app.post("/api/convert")
def convert(payload: ConvertRequest):
    try:
        local = convert_locally(payload.expression, payload.table_name, payload.calculated_field_name)
        if local.needs_ai and payload.use_ai:
            if not gemini_configured():
                return {**local.to_dict(), "method": "local-review", "ai_available": False,
                        "warnings": local.warnings + ["Gemini is not configured. Add GEMINI_API_KEY to .env to enable complex-expression conversion."]}
            try:
                ai = convert_with_gemini(payload.expression, payload.table_name, payload.calculated_field_name, payload.model_context)
                return {"dax": ai["dax"], "method": ai["method"], "needs_ai": False,
                        "warnings": ai["warnings"], "explanation": ai["explanation"], "ai_available": True}
            except Exception as exc:
                return {**local.to_dict(), "method": "local-review", "ai_available": True,
                        "warnings": local.warnings + [f"Gemini conversion failed: {str(exc)}"]}
        return {**local.to_dict(), "ai_available": gemini_configured()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/convert-file")
async def convert_file(
    file: UploadFile = File(...),
    expression_column: str = Form(""),
    table_name: str = Form(""),
    use_ai: bool = Form(False),
):
    filename = (file.filename or "").lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".xls") or filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Upload an Excel (.xlsx) or CSV (.csv) file.")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File size exceeds 10 MB.")
    try:
        import pandas as pd
        df = pd.read_csv(io.BytesIO(data)) if filename.endswith(".csv") else pd.read_excel(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read the file: {exc}") from exc
    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded file has no data rows.")
    column = expression_column.strip() or str(df.columns[0])
    if column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column '{column}' was not found. Available columns: {', '.join(map(str, df.columns))}")
    if len(df) > 500:
        raise HTTPException(status_code=400, detail="This starter version supports up to 500 rows per upload.")
    results = []
    for idx, row in df.iterrows():
        expression = "" if row[column] is None else str(row[column]).strip()
        item = {str(k): (None if pd.isna(v) else v.item() if hasattr(v, "item") else v) for k, v in row.to_dict().items()}
        if not expression or expression.lower() == "nan":
            item.update({"DAX Expression": "", "Conversion Status": "Skipped", "Conversion Method": "none", "Warnings": "Empty expression"})
        else:
            local = convert_locally(expression, table_name)
            if local.needs_ai and use_ai and gemini_configured():
                try:
                    ai = convert_with_gemini(expression, table_name)
                    item.update({"DAX Expression": ai["dax"], "Conversion Status": "AI converted - review", "Conversion Method": ai["method"], "Warnings": "; ".join(ai["warnings"])})
                except Exception as exc:
                    item.update({"DAX Expression": local.dax, "Conversion Status": "Needs review", "Conversion Method": "local-review", "Warnings": "; ".join(local.warnings + [str(exc)])})
            else:
                status = "Converted locally" if not local.needs_ai else "Needs review"
                item.update({"DAX Expression": local.dax, "Conversion Status": status, "Conversion Method": local.method, "Warnings": "; ".join(local.warnings)})
        results.append(item)
    return {"filename": file.filename, "rows": results, "count": len(results), "ai_enabled": use_ai and gemini_configured()}

# Run with: python -m uvicorn backend.main:app --reload
