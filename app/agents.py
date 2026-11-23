import json
import os
from typing import Dict, List, Tuple
import requests
from app.schemas import LoanApplication, RuleEvaluationTrace

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "240"))


def call_ollama_json(prompt: str) -> dict:
    """Calls local Ollama with JSON mode enabled and extended timeout for local CPU/GPU."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0.0,
            "num_predict": 512,
        },
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    resp.raise_for_status()
    raw = resp.json().get("response", "{}")
    return json.loads(raw)


def run_reasoning_agent(
    loan: LoanApplication,
    active_sections: Dict[str, dict],
    traces: List[RuleEvaluationTrace],
    strict_grounding: bool = False,
) -> dict:
    """
    Stage 7A: Reasoning Agent.
    Synthesizes deterministic rule traces + retrieved regulatory sections into an underwriter explanation.
    """
    strict_instruction = (
        "CRITICAL RE-QUERY MODE: Only cite section_ids present in ACTIVE_SECTIONS and copy exact substrings for quotes."
        if strict_grounding
        else ""
    )

    compact_sections = [
        {
            "section_id": s["section_id"],
            "agency": s["agency"],
            "title": s["title"],
            "verbatim_text": s["verbatim_text"],
        }
        for s in active_sections.values()
    ]

    prompt = f"""
You are a U.S. Mortgage Underwriting Compliance Reasoning Agent.
Summarize the deterministic rule traces and active guidelines concisely. Do NOT alter computed numbers.
{strict_instruction}

LOAN: id={loan.loan_id}, agency={loan.agency}, program={loan.program}, app_date={loan.application_date.isoformat()}, occupancy={loan.occupancy}

RULE_TRACES:
{json.dumps([t.model_dump() for t in traces])}

ACTIVE_SECTIONS:
{json.dumps(compact_sections)}

Return JSON with exact keys:
{{
  "summary": "2-3 concise sentences explaining rule pass/fail/missing status, overlays, and required actions.",
  "citations": [
    {{
      "section_id": "exact section_id from ACTIVE_SECTIONS",
      "quote": "exact verbatim substring from that section's verbatim_text"
    }}
  ],
  "edge_case_conflict": false
}}
"""
    return call_ollama_json(prompt)


def run_evidence_verification_agent(
    agent_output: dict,
    active_sections: Dict[str, dict],
) -> Tuple[bool, List[Dict[str, str]]]:
    """
    Stage 7B: Deterministic Evidence & Citation Verifier.
    Checks that every cited section_id exists in the temporally-valid active sections
    and that the quoted snippet actually appears in the verbatim source text.
    """
    citations = agent_output.get("citations", [])
    if not citations:
        return False, []

    verified: List[Dict[str, str]] = []
    for item in citations:
        sec_id = item.get("section_id", "").strip()
        quote = item.get("quote", "").strip()
        if sec_id not in active_sections:
            return False, []

        verbatim = active_sections[sec_id]["verbatim_text"]
        norm_verbatim = " ".join(verbatim.split()).lower()
        norm_quote = " ".join(quote.split()).lower()
        if len(norm_quote) < 10 or norm_quote not in norm_verbatim:
            return False, []

        verified.append({"section_id": sec_id, "quote": quote})

    return True, verified