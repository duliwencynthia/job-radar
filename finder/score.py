"""Scoring: fast keyword pass over everything, then Claude re-ranks the best candidates."""
from __future__ import annotations

import json
import os
import re

RESEARCH_TITLE = re.compile(r"research|scientist|phd|ph\.d|fellow|residen", re.I)


def focus_of(job: dict) -> str:
    return "research" if RESEARCH_TITLE.search(job["title"]) else "engineering"


def keyword_score(job: dict, keywords: dict[str, int]) -> int:
    title = " " + job["title"].lower() + " "
    body = " " + (job.get("description") or "").lower() + " " + (job.get("category") or "").lower() + " "
    raw = 0
    for kw, w in keywords.items():
        if kw in title:
            raw += 3 * w
        elif kw in body:
            raw += w
    degrees = " ".join(job.get("degrees") or []).lower()
    if "phd" in degrees:
        raw += 25
    elif "master" in degrees:
        raw += 8
    elif degrees and "bachelor" in degrees:
        raw -= 5
    return max(0, min(70, round(raw / 2.5)))


SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "integer", "description": "0-100 fit"},
                    "focus": {"type": "string", "enum": ["research", "engineering"]},
                    "reason": {"type": "string", "description": "one sentence, <= 25 words"},
                },
                "required": ["id", "score", "focus", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

SYSTEM = """You rank job postings for one candidate. Score each 0-100 for how worthwhile it is for this
candidate to apply. Consider: topical fit with their research (human-LLM collaboration, LLM agents, NLP,
HCI, human-subject studies) and engineering background; whether a CS PhD student is eligible (roles
limited to undergrads, sophomores, or specific schools score low); research internships at AI labs and
big-tech research orgs score highest; generic SWE internships that accept grad students are solid
(55-75); roles needing U.S. citizenship or security clearance, or unrelated fields, score under 20.
"reason" must be one concrete sentence tying the role to the candidate."""


def llm_rerank(jobs: list[dict], profile: dict, cfg: dict) -> int:
    """Mutates jobs in place with score/focus/reason from Claude. Returns how many were scored."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not jobs:
        return 0
    import anthropic

    client = anthropic.Anthropic()
    llm = cfg["llm"]
    by_id = {j["id"]: j for j in jobs}
    done = 0
    for i in range(0, len(jobs), llm["batch_size"]):
        batch = jobs[i : i + llm["batch_size"]]
        listing = [
            {
                "id": j["id"],
                "company": j["company"],
                "title": j["title"],
                "type": j["type"],
                "locations": j["locations"][:3],
                "degrees": j["degrees"],
                "sponsorship": j["sponsorship"],
                "description": (j.get("description") or "")[:1200],
            }
            for j in batch
        ]
        try:
            resp = client.beta.messages.create(
                model=llm["model"],
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                thinking={"type": "adaptive"},
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                system=SYSTEM,
                messages=[{
                    "role": "user",
                    "content": f"CANDIDATE:\n{profile['summary']}\nSeeking: {profile['seeking']}\n\n"
                               f"JOBS:\n{json.dumps(listing, ensure_ascii=False)}",
                }],
            )
        except anthropic.APIError as e:
            print(f"  rerank batch {i // llm['batch_size']} failed: {e}")
            continue
        if resp.stop_reason == "refusal":
            print(f"  rerank batch {i // llm['batch_size']} refused")
            continue
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            results = json.loads(text)["results"]
        except (json.JSONDecodeError, KeyError):
            print(f"  rerank batch {i // llm['batch_size']}: unparseable output")
            continue
        for r in results:
            j = by_id.get(r["id"])
            if j:
                j.update(score=max(0, min(100, r["score"])), focus=r["focus"], reason=r["reason"], ranked_by="claude")
                done += 1
    return done
