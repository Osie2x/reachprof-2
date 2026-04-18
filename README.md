# profreach

Automated personalized outreach pipeline for research position applications.

Upload a CSV of professor profile URLs, get back a tailored one-page PDF resume
and a 100-word draft email per professor in under two minutes. The tool does
the research and drafting work. You review and send from your own inbox.

## Origin

Built after a research-application cycle where the manual workflow (reading
each professor's page, reordering a resume, drafting a specific email) was
taking roughly 45 minutes per professor across 40+ applications. This tool
compresses the research and drafting steps to under 2 minutes each while
keeping the owner in the loop for the final send.

## What it does

- Parses a markdown library of the user's experience blocks (with tags and summaries)
- Scrapes each professor's faculty page and extracts structured metadata with Claude
- Ranks the user's experience blocks by relevance to that professor's research
- Generates a one-page PDF resume with matched blocks ordered first
- Generates a 100-word cold email draft that references one specific piece of the
  professor's research, in the user's own voice
- Saves everything to a timestamped run folder for later review and export

## What it does not do

- It does not send email. Drafts are written to text files. Sending is manual.
- It does not discover professors. The user supplies URLs.
- It does not track replies or follow-ups.

## Stack

Python · Streamlit · Anthropic Claude · httpx · BeautifulSoup · readability-lxml · Jinja2 · WeasyPrint · SQLite · Pydantic

## Quickstart

```
pip install -r requirements.txt
cp .env.example .env            # add your Anthropic API key
cp student.example.yaml student.yaml   # fill in your contact info
# edit experience_library.md and voice_samples.md
streamlit run app.py
```

## Running tests

```
pytest tests/test_smoke.py -v
```

All 20 tests run without network access or real LLM calls (LLM calls are monkeypatched).

## Scope

This is an MVP. Features deliberately out of scope for V1 are listed in PRD.md.

The decision to keep the email-sending step manual was deliberate. Canada's
Anti-Spam Legislation (CASL) governs commercial electronic messages and requires
consent and clear unsubscribe mechanisms. Personal academic outreach falls in
a different category, but automating the send step invites scrutiny that the
benefit does not justify for this tool.

## Key technical decision

Faculty pages are wildly inconsistent in structure across institutions: a large
R1 department page looks nothing like a small college faculty profile which
looks nothing like a cross-listed interdisciplinary researcher's page. Regex
or CSS-selector extraction was brittle. Pure LLM extraction occasionally
hallucinated research areas. The solution: readability-lxml strips the obvious
boilerplate, then Claude extracts structured data against a strict Pydantic
schema, then a validation pass surfaces warnings for low-confidence or
incomplete extractions so the user can decide whether to skip or hand-edit.

## License

MIT
