import json
import pickle
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import networkx as nx
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

from app.agents import run_evidence_verification_agent, run_reasoning_agent
from app.deterministic_engine import evaluate_deterministic_rules
from app.pipeline_offline import DB_PATH, GRAPH_PATH, QDRANT_PATH
from app.schemas import AssessmentStatus, FinalAssessment, LoanApplication


def stage5_temporal_hybrid_retrieval(
    loan: LoanApplication,
    expand_hops: int = 1,
) -> Tuple[Dict[str, dict], List[str], List[str]]:
    """
    Stage 5: Temporally-Filtered Hybrid Retrieval & Precedence Resolver.
    1. Queries Qdrant vector index for relevant guideline sections
    2. Traverses NetworkX Knowledge Graph for cross-referenced rules
    3. Filters out superseded rules or rules with effective_date > loan.application_date
    4. Applies Precedence Resolver (Overlay priority > Agency baseline)
    """
    _EMBEDDER= TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    qdrant = QdrantClient(path=str(QDRANT_PATH))

    query_text = (
        f"{loan.agency} {loan.program} {loan.occupancy} DTI credit score LTV reserves overlay requirements"
    )
    q_vec = list(_EMBEDDER.embed([query_text]))[0].tolist()

    hits = qdrant.query_points(
        collection_name="mortgage_guidelines",
        query=q_vec,
        limit=6,
    ).points
    qdrant.close()

    candidate_ids = {hit.payload["section_id"] for hit in hits}

    # Multi-hop Knowledge Graph expansion along CROSS_REFERENCES
    with open(GRAPH_PATH, "rb") as f:
        kg: nx.DiGraph = pickle.load(f)

    expanded_ids = set(candidate_ids)
    for _ in range(expand_hops):
        next_ids = set()
        for cid in expanded_ids:
            if cid in kg:
                for neighbor in kg.neighbors(cid):
                    edge = kg.get_edge_data(cid, neighbor)
                    if edge and edge.get("relation") == "CROSS_REFERENCES":
                        next_ids.add(neighbor)
        expanded_ids.update(next_ids)

    # Fetch exact records from SQLite Source Store & apply Temporal Filter
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT * FROM source_sections WHERE section_id IN ({','.join(['?']*len(expanded_ids))})",
        tuple(expanded_ids),
    ).fetchall()
    conn.close()

    active_sections: Dict[str, dict] = {}
    superseded_filtered: List[str] = []

    for row in rows:
        sec = dict(row)
        eff_date = datetime.fromisoformat(sec["effective_date"]).date()
        # Temporal check: rule must be effective on or before loan application_date
        if eff_date > loan.application_date:
            superseded_filtered.append(f"{sec['section_id']} (not yet effective on {loan.application_date})")
            continue
        if sec["superseded_by"]:
            superseded_filtered.append(f"{sec['section_id']} (superseded by {sec['superseded_by']})")
            continue
        active_sections[sec["section_id"]] = sec

    # Precedence Resolver: check if an Overlay overrides a baseline rule
    overlay_overrides: List[str] = []
    if "OVERLAY-DTI-01" in active_sections and "B3-6-02" in active_sections:
        overlay_overrides.append("OVERLAY-DTI-01 overrides Fannie Mae B3-6-02 (Max DTI capped at 45.0%)")

    return active_sections, superseded_filtered, overlay_overrides


def evaluate_loan_compliance(loan: LoanApplication) -> FinalAssessment:
    """
    Executes Part B end-to-end:
    Stage 4 (Intake) -> Stage 5 (Hybrid Retrieval) -> Stage 6 (Deterministic Engine)
    -> Stage 7 (Multi-Agent Synthesis & Citation Verification + Re-query Loop)
    -> Stage 8 (Final Assessment) -> Stage 9 (Immutable SQLite Audit Log)
    """
    # Stage 5: Hybrid Retrieval + Temporal Filter + Precedence
    active_sections, superseded_filtered, overlay_overrides = stage5_temporal_hybrid_retrieval(loan, expand_hops=1)

    # Stage 6: Deterministic Rule Engine
    traces = evaluate_deterministic_rules(loan, active_sections)

    # Stage 7: Multi-Agent Reasoning + Citation Verification (with 1 re-query retry loop)
    requery_triggered = False
    agent_out = run_reasoning_agent(loan, active_sections, traces, strict_grounding=False)
    verified_ok, verified_citations = run_evidence_verification_agent(agent_out, active_sections)

    if not verified_ok:
        requery_triggered = True
        active_sections, superseded_filtered, overlay_overrides = stage5_temporal_hybrid_retrieval(loan, expand_hops=2)
        agent_out = run_reasoning_agent(loan, active_sections, traces, strict_grounding=True)
        verified_ok, verified_citations = run_evidence_verification_agent(agent_out, active_sections)

    # Stage 8: Auditable Final Assessment Decision Logic
    statuses = {t.status for t in traces}
    if "FAIL" in statuses:
        final_status = AssessmentStatus.FAIL
    elif "MISSING_INPUT" in statuses:
        final_status = AssessmentStatus.INSUFFICIENT_EVIDENCE
    elif not verified_ok or agent_out.get("edge_case_conflict", False):
        final_status = AssessmentStatus.MANUAL_REVIEW
    else:
        final_status = AssessmentStatus.PASS

    audit_id = f"AUD-{uuid.uuid4().hex[:10].upper()}"
    assessment = FinalAssessment(
        loan_id=loan.loan_id,
        status=final_status,
        applied_rules_count=len(traces),
        superseded_rules_filtered=superseded_filtered,
        overlay_overrides_applied=overlay_overrides,
        deterministic_traces=traces,
        reasoning_summary=agent_out.get("summary", ""),
        verified_citations=verified_citations,
        citation_verification_passed=verified_ok,
        requery_triggered=requery_triggered,
        audit_id=audit_id,
    )

    # Stage 9: Persist Immutable Audit Record
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO audit_logs
        (audit_id, timestamp, loan_id, status, payload_json, assessment_json, hitl_override_status, hitl_reviewer, hitl_notes)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """,
        (
            audit_id,
            datetime.now(timezone.utc).isoformat(),
            loan.loan_id,
            final_status.value,
            loan.model_dump_json(),
            assessment.model_dump_json(),
        ),
    )
    conn.commit()
    conn.close()

    return assessment