# Job Radar (Agent 1)

A daily job-finding agent for **Summer 2027 internships** (research and engineering) plus selected
full-time roles, ranked against my background in human–LLM collaboration, NLP and software engineering.

**Live page:** https://duliwencynthia.github.io/job-radar/

## How it works

1. **Collect.** A GitHub Action runs every morning. It pulls [SimplifyJobs](https://github.com/SimplifyJobs)
   internship and new-grad listings, and polls Greenhouse, Ashby and Lever boards for research labs
   (see `config.yaml`).
2. **Filter.** Keeps Summer 2027 terms and software or AI/ML categories. Drops senior, undergrad-only and
   citizenship-required roles.
3. **Score.** A keyword pass (`profile.yaml`) ranks everything. If an `ANTHROPIC_API_KEY` repo secret exists,
   Claude re-scores the top new candidates and writes a one-line reason. Earlier Claude verdicts are cached,
   so each day only new jobs cost tokens.
4. **Publish.** Writes `docs/jobs.json` and deploys `docs/` to GitHub Pages.

Agent 2 (a separate local tool, not in this repo) reads `jobs.json` to tailor my resume and pre-fill applications.

## Configure

- `config.yaml`: terms, categories, company boards, filters, Claude settings.
- `profile.yaml`: public-safe profile summary and keyword weights.
- To enable Claude ranking, open Settings → Secrets and variables → Actions → New repository secret,
  and add `ANTHROPIC_API_KEY`.
- To run it manually, use Actions → *Find jobs* → Run workflow.

Local run: `pip install -r requirements.txt && python -m finder.main`
