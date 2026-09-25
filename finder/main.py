"""Agent 1 entry point: collect -> filter -> score -> write docs/jobs.json for the GitHub Pages site.

Run locally:  python -m finder.main
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import score, sources

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "jobs.json"


def load_yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())


def keep(job: dict, cfg: dict, exclude: list[re.Pattern]) -> bool:
    if job["source"] == "simplify" and job["category"] not in cfg["categories"]:
        return False
    if cfg.get("exclude_citizenship_required") and "citizenship" in (job.get("sponsorship") or "").lower():
        return False
    if any(p.search(job["title"]) for p in exclude):
        return False
    return bool(job.get("url"))


def dedupe(jobs: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for j in jobs:
        key = (j["company"].lower().strip(), j["title"].lower().strip())
        if key not in seen or (j["description"] and not seen[key]["description"]):
            seen[key] = j
    return list(seen.values())


def keyword_reason(job: dict, keywords: dict) -> str:
    text = (job["title"] + " " + job.get("description", "")).lower()
    hits = [k.strip() for k in sorted(keywords, key=keywords.get, reverse=True) if k in text][:4]
    extra = " PhD listed as eligible." if "PhD" in " ".join(job.get("degrees") or []) else ""
    return (f"Keyword match: {', '.join(hits)}." if hits else "Broad match on role type.") + extra


def main() -> None:
    cfg, profile = load_yaml("config.yaml"), load_yaml("profile.yaml")
    previous = {}
    if OUT.exists():
        previous = {j["id"]: j for j in json.loads(OUT.read_text()).get("jobs", [])}

    print("Collecting…")
    jobs, errors = sources.collect(cfg)
    exclude = [re.compile(p, re.I) for p in cfg["exclude_title_patterns"]]
    jobs = dedupe([j for j in jobs if keep(j, cfg, exclude)])
    print(f"{len(jobs)} jobs after filtering")

    today = datetime.now(timezone.utc).date().isoformat()
    for j in jobs:
        j["focus"] = score.focus_of(j)
        j["score"] = score.keyword_score(j, profile["keywords"])
        j["reason"] = keyword_reason(j, profile["keywords"])
        j["ranked_by"] = "keywords"
        prev = previous.get(j["id"])
        j["first_seen"] = prev["first_seen"] if prev else today
        if prev and prev.get("ranked_by") == "claude":  # reuse earlier Claude verdicts; saves tokens
            j.update(score=prev["score"], focus=prev["focus"], reason=prev["reason"], ranked_by="claude")

    jobs.sort(key=lambda j: j["score"], reverse=True)
    todo = [j for j in jobs if j["ranked_by"] != "claude"][: cfg["llm"]["rerank_top_n"]]
    n = score.llm_rerank(todo, profile, cfg)
    print(f"Claude re-ranked {n} new jobs")

    jobs.sort(key=lambda j: (j["score"], j["posted"] or ""), reverse=True)
    jobs = jobs[: cfg["max_jobs_on_page"]]
    for j in jobs:
        j["description"] = j["description"][:600]  # keep the page light; Agent 2 re-fetches full JDs

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "candidate": profile["name"],
        "counts": {
            "internship": sum(j["type"] == "internship" for j in jobs),
            "fulltime": sum(j["type"] == "fulltime" for j in jobs),
        },
        "source_errors": errors,
        "jobs": jobs,
    }, indent=1, ensure_ascii=False))
    print(f"Wrote {len(jobs)} jobs to {OUT}")


if __name__ == "__main__":
    main()
