import sqlite3
from fastapi import FastAPI
from pydantic import BaseModel
from app.pipeline_offline import DB_PATH, run_offline_ingestion
from app.pipeline_online import evaluate_loan_compliance
from app.schemas import FinalAssessment, LoanApplication

app = FastAPI(title="U.S. Mortgage Compliance KG-RAG Prototype")


class HitlOverrideRequest(BaseModel):
    audit_id: str
    override_status: str
    reviewer_name: str
    notes: str


@app.post("/ingest")
def ingest_regulations():
    stats = run_offline_ingestion()
    return {"message": "Offline knowledge pipeline completed", "stats": stats}


@app.post("/evaluate", response_model=FinalAssessment)
def evaluate_loan(loan: LoanApplication):
    return evaluate_loan_compliance(loan)


@app.post("/hitl-override")
def hitl_override(req: HitlOverrideRequest):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE audit_logs
        SET hitl_override_status = ?, hitl_reviewer = ?, hitl_notes = ?
        WHERE audit_id = ?
        """,
        (req.override_status, req.reviewer_name, req.notes, req.audit_id),
    )
    conn.commit()
    conn.close()
    return {"message": "HITL underwriter override recorded", "audit_id": req.audit_id}


@app.get("/audit-logs")
def get_audit_logs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]