from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

app = FastAPI(title="Career Assessment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Google Sheets setup ──────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    sheet_id   = os.environ.get("GOOGLE_SHEET_ID")

    if not creds_json or not sheet_id:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_CREDENTIALS_JSON or GOOGLE_SHEET_ID env vars")

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)

    # Get or create "Raw Responses" sheet
    try:
        sheet = spreadsheet.worksheet("Raw Responses")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Raw Responses", rows=10000, cols=35)
        _write_headers(sheet)

    return sheet

def _write_headers(sheet):
    headers = [
        "Response ID", "Timestamp", "Session Token",
        "Q1 (Power)", "Q2 (Ambiguity)", "Q3 (Identity)", "Q4 (Politics)", "Q5 (Ownership)",
        "Q6 (Collab)", "Q7 (Power)", "Q8 (Ambiguity)", "Q9 (Identity)", "Q10 (Politics)",
        "Q11 (Ownership)", "Q12 (Collab)", "Q13 (Power)", "Q14 (Ambiguity)", "Q15 (Identity)",
        "Q16 (Politics)", "Q17 (Ownership)", "Q18 (Collab)",
        "Agency %", "Expert %", "Politics %", "Business %",
        "Archetype", "Environment Fit",
    ]
    sheet.append_row(headers, value_input_option="RAW")

# ── Models ───────────────────────────────────────────────────────────────
class Scores(BaseModel):
    agency: int
    expert: int
    politics: int
    business: int

class SubmitRequest(BaseModel):
    session_id: str
    answers: List[str]           # ["A","C","B", ...]
    scores: Scores
    archetype: str
    environment: str

class SubmitResponse(BaseModel):
    ok: bool
    response_id: str
    message: str

# ── Routes ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/api/submit", response_model=SubmitResponse)
def submit(payload: SubmitRequest):
    try:
        sheet = get_sheet()
        response_id = f"RSP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{payload.session_id[-4:]}"
        timestamp   = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        row = [
            response_id,
            timestamp,
            payload.session_id,
            *payload.answers,           # Q1–Q18, each a letter
            payload.scores.agency,
            payload.scores.expert,
            payload.scores.politics,
            payload.scores.business,
            payload.archetype,
            payload.environment,
        ]

        sheet.append_row(row, value_input_option="USER_ENTERED")

        return SubmitResponse(ok=True, response_id=response_id, message="Saved successfully")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/responses")
def get_responses():
    """Return all responses as JSON (useful for analytics)."""
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        return {"ok": True, "count": len(records), "data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Serve static frontend ────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse("static/index.html")
