from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AssessmentStatus(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    INSUFFICIENT_EVIDENCE = "Insufficient Evidence"
    MANUAL_REVIEW = "Manual Review"
    ERROR = "System Error"


class RegulatorySection(BaseModel):
    section_id: str
    agency: str                       # e.g., "Fannie Mae", "Lender Overlay"
    program: str                      # e.g., "Conventional"
    title: str
    effective_date: date
    superseded_by: Optional[str] = None
    overlay_priority: int = 1         # 1 = Agency Baseline, 2 = Investor/Lender Overlay
    verbatim_text: str
    cross_references: List[str] = Field(default_factory=list)
    triplets: List[List[str]] = Field(default_factory=list)  # [[S, P, O], ...]


class LoanFact(BaseModel):
    value: Any
    source_doc: str
    page: int


class LoanApplication(BaseModel):
    loan_id: str
    agency: str = "Fannie Mae"
    program: str = "Conventional"
    application_date: date
    occupancy: str                    # "Primary Residence", "Investment"
    property_type: str                # "Single Family", "Condo"
    credit_score: Optional[LoanFact] = None
    gross_monthly_income: Optional[LoanFact] = None
    monthly_debt_obligations: Optional[LoanFact] = None
    loan_amount: Optional[LoanFact] = None
    appraised_value: Optional[LoanFact] = None
    liquid_reserves_months: Optional[LoanFact] = None
    aus_recommendation: Optional[LoanFact] = None  # "Approve/Eligible", "Manual"


class RuleEvaluationTrace(BaseModel):
    rule_id: str
    section_id: str
    governing_authority: str
    rule_name: str
    status: str                       # "PASS", "FAIL", "MISSING_INPUT"
    computed_value: Optional[float] = None
    threshold: Optional[float] = None
    operator: str
    formula: str
    evidence_provenance: str


class FinalAssessment(BaseModel):
    loan_id: str
    status: AssessmentStatus
    applied_rules_count: int
    superseded_rules_filtered: List[str]
    overlay_overrides_applied: List[str]
    deterministic_traces: List[RuleEvaluationTrace]
    reasoning_summary: str
    verified_citations: List[Dict[str, str]]
    citation_verification_passed: bool
    requery_triggered: bool
    audit_id: str