"""Job sources: Simplify's curated listings plus direct company ATS boards."""
from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "career-agents-finder/1.0 (+https://github.com/duliwencynthia)"}
SIMPLIFY = "https://raw.githubusercontent.com/SimplifyJobs/{repo}/dev/.github/scripts/listings.json"

EARLY_CAREER = re.compile(
    r"\b(intern|internship|co-?op|fellow|fellowship|residen(t|cy)|phd|ph\.d|new grad|university grad|graduate|early career|student)\b",
    re.I,
)


def _get_json(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _strip_html(s: str | None, limit: int = 4000) -> str:
    if not s:
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(s)))
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _iso(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    return str(ts)[:10]


def simplify_internships(cfg) -> list[dict]:
    data = _get_json(SIMPLIFY.format(repo="Summer2026-Internships"))
    terms = set(cfg["terms"])
    out = []
    for x in data:
        if not (x.get("active") and x.get("is_visible")):
            continue
        if not terms.intersection(x.get("terms") or []):
            continue
        out.append(_from_simplify(x, "internship"))
    return out


def simplify_fulltime(cfg) -> list[dict]:
    data = _get_json(SIMPLIFY.format(repo="New-Grad-Positions"))
    cutoff = time.time() - cfg["fulltime_max_age_days"] * 86400
    out = []
    for x in data:
        if not (x.get("active") and x.get("is_visible")):
            continue
        if (x.get("date_posted") or 0) < cutoff:
            continue
        out.append(_from_simplify(x, "fulltime"))
    return out


def _from_simplify(x: dict, kind: str) -> dict:
    return {
        "id": "s-" + x["id"][:12],
        "company": x.get("company_name", ""),
        "title": x.get("title", ""),
        "url": x.get("url", ""),
        "locations": x.get("locations") or [],
        "type": kind,
        "category": x.get("category", ""),
        "degrees": x.get("degrees") or [],
        "sponsorship": x.get("sponsorship", ""),
        "posted": _iso(x.get("date_posted")),
        "description": "",
        "source": "simplify",
    }


def greenhouse(token: str) -> list[dict]:
    d = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in d.get("jobs", []):
        if not EARLY_CAREER.search(j["title"]):
            continue
        out.append({
            "id": f"gh-{token}-{j['id']}",
            "company": j.get("company_name") or token.title(),
            "title": j["title"],
            "url": j["absolute_url"],
            "locations": [j.get("location", {}).get("name", "")],
            "type": _kind(j["title"]),
            "category": "",
            "degrees": [],
            "sponsorship": "",
            "posted": _iso(j.get("first_published") or j.get("updated_at")),
            "description": _strip_html(j.get("content")),
            "source": "greenhouse",
        })
    return out


def ashby(org: str) -> list[dict]:
    d = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{org}")
    out = []
    for j in d.get("jobs", []):
        if not j.get("isListed", True) or not EARLY_CAREER.search(j["title"]):
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        out.append({
            "id": f"ab-{org}-{j['id'][:12]}",
            "company": org.title(),
            "title": j["title"],
            "url": j.get("jobUrl") or j.get("applyUrl"),
            "locations": [l for l in locs if l],
            "type": _kind(j["title"]),
            "category": j.get("department") or "",
            "degrees": [],
            "sponsorship": "",
            "posted": _iso(j.get("publishedAt")),
            "description": (j.get("descriptionPlain") or "")[:4000],
            "source": "ashby",
        })
    return out


def lever(org: str) -> list[dict]:
    d = _get_json(f"https://api.lever.co/v0/postings/{org}?mode=json")
    out = []
    for j in d:
        if not EARLY_CAREER.search(j["text"]):
            continue
        cats = j.get("categories") or {}
        out.append({
            "id": f"lv-{org}-{j['id'][:12]}",
            "company": org.title(),
            "title": j["text"],
            "url": j.get("hostedUrl"),
            "locations": [cats.get("location", "")],
            "type": _kind(j["text"]),
            "category": cats.get("team", ""),
            "degrees": [],
            "sponsorship": "",
            "posted": _iso((j.get("createdAt") or 0) / 1000 or None),
            "description": (j.get("descriptionPlain") or "")[:4000],
            "source": "lever",
        })
    return out


def _kind(title: str) -> str:
    return "internship" if re.search(r"\b(intern|internship|co-?op)\b", title, re.I) else "fulltime"


def collect(cfg) -> tuple[list[dict], list[str]]:
    """Returns (jobs, errors). A failing source never kills the run."""
    jobs, errors = [], []
    tasks = [("simplify-internships", lambda: simplify_internships(cfg))]
    if cfg.get("include_fulltime"):
        tasks.append(("simplify-fulltime", lambda: simplify_fulltime(cfg)))
    fetchers = {"greenhouse": greenhouse, "ashby": ashby, "lever": lever}
    for kind, orgs in (cfg.get("boards") or {}).items():
        for org in orgs or []:
            tasks.append((f"{kind}:{org}", lambda f=fetchers[kind], o=org: f(o)))
    for name, fn in tasks:
        try:
            got = fn()
            print(f"  {name}: {len(got)}")
            jobs.extend(got)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            print(f"  {name}: ERROR {e}")
    return jobs, errors
