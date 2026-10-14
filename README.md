# FormulaFlow — Tableau to DAX Converter (MVP)

A local-first web application with an HTML/CSS/vanilla JavaScript frontend and a Python FastAPI backend. Supported expressions are translated with local rules; complex expressions can be sent to Gemini only when AI fallback is enabled.

## Requirements
- Python 3.10+
- A Gemini API key only if you want AI-assisted conversion of complex expressions

## Run locally (Windows PowerShell)

```powershell
cd path\to\tableau_dax_converter
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and set `GEMINI_API_KEY` if you want the AI fallback. Keep the key private and do not commit `.env` to Git. If you leave the key empty, local conversions still work and complex expressions are flagged for review without making an API call.

Start the app:

```powershell
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000

API docs: http://127.0.0.1:8000/docs

## Run tests

```powershell
python -m pytest -q
```

## Current MVP capabilities
- Single-expression conversion
- Local mappings for common aggregations, simple conditionals, logical operators, and selected string/null functions
- Optional Gemini fallback for complex expressions
- Optional target table and model context
- Excel/CSV upload with per-row status and downloadable CSV output
- API health endpoint at `/api/health`

## Important limitations
This is a starter converter, not a guarantee of semantic equivalence for every Tableau expression. LOD expressions, table calculations, context-dependent aggregations, date behavior, sets, and parameters may require model-specific translation. Review generated DAX in Power BI, especially for production migration.

The bulk endpoint supports up to 500 rows and 10 MB per file. The current downloadable bulk output is CSV; source rows are retained as output columns.
