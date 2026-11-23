from datetime import date
from app.schemas import RegulatorySection

REGULATORY_DOCUMENTS: list[RegulatorySection] = [
    RegulatorySection(
        section_id="B3-6-02-OLD",
        agency="Fannie Mae",
        program="Conventional",
        title="Debt-to-Income Ratios (Superseded 2023 Rule)",
        effective_date=date(2023, 1, 1),
        superseded_by="B3-6-02",
        overlay_priority=1,
        verbatim_text=(
            "For manually underwritten loans, the maximum total DTI ratio is 36%, "
            "or up to 45% if the borrower meets credit score and reserve requirements."
        ),
        cross_references=["B3-5.1-01", "B3-4.1-01"],
        triplets=[
            ["Manually Underwritten Loan", "has_max_dti", "36%"],
            ["Manually Underwritten Loan", "allows_extended_dti_up_to", "45%"],
        ],
    ),
    RegulatorySection(
        section_id="B3-6-02",
        agency="Fannie Mae",
        program="Conventional",
        title="Debt-to-Income Ratios (Current Guideline)",
        effective_date=date(2024, 6, 1),
        superseded_by=None,
        overlay_priority=1,
        verbatim_text=(
            "For DU casefiles receiving Approve/Eligible, the maximum allowable total DTI ratio is 50%. "
            "For manually underwritten loans, the baseline maximum DTI is 36%, extendable to 45% with compensating factors."
        ),
        cross_references=["B3-5.1-01", "B3-4.1-01"],
        triplets=[
            ["DU Approve/Eligible Loan", "has_max_dti", "50%"],
            ["Manually Underwritten Loan", "has_baseline_max_dti", "36%"],
            ["B3-6-02", "cross_references", "B3-5.1-01"],
            ["B3-6-02", "cross_references", "B3-4.1-01"],
        ],
    ),
    RegulatorySection(
        section_id="OVERLAY-DTI-01",
        agency="Lender Overlay",
        program="Conventional",
        title="Internal Credit Policy Overlay — Maximum DTI Cap",
        effective_date=date(2025, 1, 15),
        superseded_by=None,
        overlay_priority=2,  # Stricter than Fannie Mae baseline
        verbatim_text=(
            "Lender Overlay Policy: Regardless of DU Approve/Eligible findings, total DTI ratio "
            "must not exceed 45.0% for all Conventional loans originated on or after January 15, 2025."
        ),
        cross_references=["B3-6-02"],
        triplets=[
            ["Lender Overlay", "overrides", "B3-6-02"],
            ["Conventional Loan", "has_overlay_max_dti", "45.0%"],
        ],
    ),
    RegulatorySection(
        section_id="B3-5.1-01",
        agency="Fannie Mae",
        program="Conventional",
        title="General Requirements for Credit Scores",
        effective_date=date(2024, 1, 1),
        superseded_by=None,
        overlay_priority=1,
        verbatim_text=(
            "The minimum representative credit score for conventional fixed-rate loans is 620. "
            "Loans with credit scores below 620 are ineligible for delivery to Fannie Mae."
        ),
        cross_references=["B3-6-02"],
        triplets=[
            ["Conventional Fixed-Rate Loan", "requires_min_fico", "620"],
            ["Credit Score Below 620", "results_in", "Ineligible"],
        ],
    ),
    RegulatorySection(
        section_id="B2-1.2-01",
        agency="Fannie Mae",
        program="Conventional",
        title="Loan-to-Value (LTV) Ratios — Primary Residence Purchase",
        effective_date=date(2024, 1, 1),
        superseded_by=None,
        overlay_priority=1,
        verbatim_text=(
            "For a 1-unit principal residence purchase transaction underwritten through DU, "
            "the maximum allowable LTV ratio is 97% (or 95% for standard non-HomeReady fixed-rate loans)."
        ),
        cross_references=["B3-4.1-01"],
        triplets=[
            ["1-Unit Primary Residence", "has_max_ltv", "95%"],
        ],
    ),
    RegulatorySection(
        section_id="B3-4.1-01",
        agency="Fannie Mae",
        program="Conventional",
        title="Minimum Reserve Requirements",
        effective_date=date(2024, 1, 1),
        superseded_by=None,
        overlay_priority=1,
        verbatim_text=(
            "For a 1-unit principal residence transaction with LTV greater than 80%, "
            "a minimum of 2 months of liquid PITIA reserves is required when DTI exceeds 40%."
        ),
        cross_references=["B3-6-02", "B2-1.2-01"],
        triplets=[
            ["1-Unit Primary Residence LTV > 80%", "requires_min_reserves", "2 months"],
        ],
    ),
]