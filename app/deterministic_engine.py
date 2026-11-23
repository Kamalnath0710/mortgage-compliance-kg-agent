from typing import Dict, List
from app.schemas import LoanApplication, RuleEvaluationTrace


def evaluate_deterministic_rules(
    loan: LoanApplication,
    active_sections: Dict[str, dict],
) -> List[RuleEvaluationTrace]:
    """
    Stage 6: Runs BEFORE final LLM reasoning.
    Executes exact mathematical formulas, threshold comparisons, and missing-input checks
    bound to the active, temporally-valid governing sections.
    """
    traces: List[RuleEvaluationTrace] = []

    # 1. DTI Check (Resolves Fannie Mae B3-6-02 vs Lender Overlay OVERLAY-DTI-01)
    if "OVERLAY-DTI-01" in active_sections:
        dti_section = active_sections["OVERLAY-DTI-01"]
        max_dti = 45.0
        authority = "Lender Overlay (Overrides Fannie Mae B3-6-02)"
    else:
        dti_section = active_sections.get("B3-6-02", {})
        aus = loan.aus_recommendation.value if loan.aus_recommendation else "Manual"
        max_dti = 50.0 if aus == "Approve/Eligible" else 36.0
        authority = "Fannie Mae Baseline"

    if loan.gross_monthly_income and loan.monthly_debt_obligations:
        income = float(loan.gross_monthly_income.value)
        debt = float(loan.monthly_debt_obligations.value)
        computed_dti = round((debt / income) * 100, 2) if income > 0 else 999.0
        status = "PASS" if computed_dti <= max_dti else "FAIL"
        provenance = (
            f"Debt ${debt:,.2f} ({loan.monthly_debt_obligations.source_doc} p.{loan.monthly_debt_obligations.page}) / "
            f"Income ${income:,.2f} ({loan.gross_monthly_income.source_doc} p.{loan.gross_monthly_income.page})"
        )
    else:
        computed_dti = None
        status = "MISSING_INPUT"
        provenance = "Missing gross_monthly_income or monthly_debt_obligations"

    traces.append(
        RuleEvaluationTrace(
            rule_id="RULE-DTI-MAX",
            section_id=dti_section.get("section_id", "B3-6-02"),
            governing_authority=authority,
            rule_name="Maximum Total Debt-to-Income (DTI) Ratio",
            status=status,
            computed_value=computed_dti,
            threshold=max_dti,
            operator="<=",
            formula="(monthly_debt_obligations / gross_monthly_income) * 100",
            evidence_provenance=provenance,
        )
    )

    # 2. Credit Score Check (B3-5.1-01)
    min_fico = 620.0
    if loan.credit_score:
        fico_val = float(loan.credit_score.value)
        fico_status = "PASS" if fico_val >= min_fico else "FAIL"
        fico_prov = f"FICO {int(fico_val)} ({loan.credit_score.source_doc} p.{loan.credit_score.page})"
    else:
        fico_val = None
        fico_status = "MISSING_INPUT"
        fico_prov = "Missing credit_score"

    traces.append(
        RuleEvaluationTrace(
            rule_id="RULE-FICO-MIN",
            section_id="B3-5.1-01",
            governing_authority="Fannie Mae Baseline",
            rule_name="Minimum Representative Credit Score",
            status=fico_status,
            computed_value=fico_val,
            threshold=min_fico,
            operator=">=",
            formula="representative_fico >= 620",
            evidence_provenance=fico_prov,
        )
    )

    # 3. LTV Ratio Check (B2-1.2-01)
    max_ltv = 95.0
    if loan.loan_amount and loan.appraised_value:
        l_amt = float(loan.loan_amount.value)
        a_val = float(loan.appraised_value.value)
        computed_ltv = round((l_amt / a_val) * 100, 2) if a_val > 0 else 999.0
        ltv_status = "PASS" if computed_ltv <= max_ltv else "FAIL"
        ltv_prov = (
            f"Loan ${l_amt:,.2f} ({loan.loan_amount.source_doc} p.{loan.loan_amount.page}) / "
            f"Value ${a_val:,.2f} ({loan.appraised_value.source_doc} p.{loan.appraised_value.page})"
        )
    else:
        computed_ltv = None
        ltv_status = "MISSING_INPUT"
        ltv_prov = "Missing loan_amount or appraised_value"

    traces.append(
        RuleEvaluationTrace(
            rule_id="RULE-LTV-MAX",
            section_id="B2-1.2-01",
            governing_authority="Fannie Mae Baseline",
            rule_name="Maximum Loan-to-Value (LTV) Ratio",
            status=ltv_status,
            computed_value=computed_ltv,
            threshold=max_ltv,
            operator="<=",
            formula="(loan_amount / appraised_value) * 100",
            evidence_provenance=ltv_prov,
        )
    )

    # 4. Conditional Liquid Reserves Check (B3-4.1-01: triggered if LTV > 80% and DTI > 40%)
    if computed_ltv is not None and computed_dti is not None:
        if computed_ltv > 80.0 and computed_dti > 40.0:
            req_reserves = 2.0
            if loan.liquid_reserves_months is not None:
                res_val = float(loan.liquid_reserves_months.value)
                res_status = "PASS" if res_val >= req_reserves else "FAIL"
                res_prov = f"Reserves {res_val} mos ({loan.liquid_reserves_months.source_doc} p.{loan.liquid_reserves_months.page})"
            else:
                res_val = None
                res_status = "MISSING_INPUT"
                res_prov = "Missing liquid_reserves_months (required when LTV > 80% and DTI > 40%)"

            traces.append(
                RuleEvaluationTrace(
                    rule_id="RULE-RESERVES-COND",
                    section_id="B3-4.1-01",
                    governing_authority="Fannie Mae Baseline",
                    rule_name="Conditional PITIA Liquid Reserves (LTV > 80% & DTI > 40%)",
                    status=res_status,
                    computed_value=res_val,
                    threshold=req_reserves,
                    operator=">=",
                    formula="liquid_reserves_months >= 2 when LTV > 80% and DTI > 40%",
                    evidence_provenance=res_prov,
                )
            )

    return traces