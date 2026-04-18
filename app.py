"""profreach Streamlit application.

Three sidebar pages:
  1. Library   -- display parsed experience_library.md and voice_samples.md
  2. Scrape & Match -- run the full pipeline
  3. Review & Export -- browse past runs, download PDFs, copy email drafts
"""

import csv
import io
import re
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import yaml

from profreach.config import (
    DB_PATH,
    EXPERIENCE_LIBRARY_PATH,
    FIXTURES_DIR,
    RUNS_DIR,
    STUDENT_YAML_PATH,
    VOICE_SAMPLES_PATH,
)
from profreach.db import (
    get_professor_records_for_run,
    init_db,
    insert_professor_record,
    insert_run,
    list_runs,
    update_run_counts,
)
from profreach.drafting import draft_email
from profreach.extraction import extract_professor
from profreach.library import load_voice_samples, parse_library
from profreach.matching import match_blocks
from profreach.models import ProfessorInput, ProfessorRecord, Run, StudentInfo
from profreach.resume import render_resume
from profreach.scraping import fetch_page, html_to_clean_text, load_fixture
from profreach.validation import validate_extraction

st.set_page_config(page_title="profreach", layout="wide")

# initialise DB on startup
init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40]


def _load_student() -> StudentInfo | None:
    if not STUDENT_YAML_PATH.exists():
        return None
    with open(STUDENT_YAML_PATH) as f:
        d = yaml.safe_load(f)
    return StudentInfo(
        name=d.get("name", "Student"),
        email=d.get("email", ""),
        phone=d.get("phone", ""),
        location=d.get("location", ""),
        github=d.get("github", ""),
        linkedin=d.get("linkedin", ""),
    )


def _load_library():
    if not EXPERIENCE_LIBRARY_PATH.exists():
        return []
    with open(EXPERIENCE_LIBRARY_PATH) as f:
        return parse_library(f.read())


def _load_voice() -> str:
    if not VOICE_SAMPLES_PATH.exists():
        return ""
    with open(VOICE_SAMPLES_PATH) as f:
        return load_voice_samples(f.read())


def _fixture_url_map() -> dict[str, Path]:
    return {
        f.name: f for f in sorted(FIXTURES_DIR.glob("*.html"))
    }


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    professors: list[ProfessorInput],
    use_fixtures: bool,
    run_id: str,
    log_placeholder,
) -> tuple[int, int]:
    """Run the full pipeline for a list of professors. Returns (success, failure)."""
    student = _load_student()
    blocks = _load_library()
    voice = _load_voice()
    # load student context field from yaml for the drafting prompt
    student_yaml_context = ""
    if STUDENT_YAML_PATH.exists():
        with open(STUDENT_YAML_PATH) as f:
            _sy = yaml.safe_load(f)
            student_yaml_context = _sy.get("context", "")

    fixture_map = _fixture_url_map()
    fixture_files = sorted(fixture_map.values())

    logs: list[str] = []
    success = 0
    failure = 0

    def log(msg: str):
        logs.append(msg)
        log_placeholder.text("\n".join(logs[-30:]))

    for i, prof_input in enumerate(professors):
        prof_url = prof_input.url
        prof_name_hint = prof_input.name or ""
        log(f"\n[{i+1}/{len(professors)}] Processing: {prof_url}")

        try:
            # --- scrape ---
            if use_fixtures:
                # cycle through fixtures
                fixture_path = fixture_files[i % len(fixture_files)]
                log(f"  Loading fixture: {fixture_path.name}")
                raw_html = load_fixture(str(fixture_path))
                page_url_for_extraction = f"fixture://{fixture_path.name}"
            else:
                log(f"  Fetching page...")
                raw_html = fetch_page(prof_url)
                page_url_for_extraction = prof_url

            page_text = html_to_clean_text(raw_html)
            log(f"  Extracted {len(page_text)} chars of clean text")

            # --- extract ---
            log("  Extracting professor metadata via LLM...")
            prof = extract_professor(
                page_text=page_text,
                page_url=page_url_for_extraction,
                user_note=prof_input.note or "",
            )
            log(f"  Extracted: {prof.name} | {prof.university} | research_areas={prof.research_areas[:2]}...")

            # --- validate ---
            warnings = validate_extraction(prof)
            for w in warnings:
                log(f"  WARNING: {w}")

            # --- match ---
            log("  Matching experience blocks...")
            match = match_blocks(professor=prof, blocks=blocks)
            log(f"  Matched {len(match.top_blocks)} blocks: {[b.id for b in match.top_blocks]}")

            # --- draft email ---
            log("  Drafting email...")
            email_draft = draft_email(
                professor=prof,
                top_blocks=match.top_blocks,
                voice_samples_text=voice,
                student_name=student.name if student else "Osie",
                student_context=student_yaml_context or "First-year BBA/CS student, Wilfrid Laurier University",
            )
            log(f"  Email draft: {email_draft.word_count} words")

            # --- render resume ---
            prof_slug = _slugify(prof.name) or f"prof-{i}"
            run_dir = RUNS_DIR / run_id / prof_slug
            run_dir.mkdir(parents=True, exist_ok=True)

            resume_path = run_dir / "resume.pdf"
            email_path = run_dir / "email.txt"

            ordered_blocks = match.top_blocks + [
                b for b in blocks if b not in match.top_blocks
            ]

            if student:
                log("  Rendering resume PDF...")
                render_resume(
                    student=student,
                    ordered_blocks=ordered_blocks,
                    output_path=resume_path,
                )
                resume_pdf_path_str = str(resume_path)
            else:
                log("  Skipping PDF render -- student.yaml not found.")
                resume_pdf_path_str = ""

            # --- write email ---
            email_path.write_text(
                f"Subject: {email_draft.subject}\n\n{email_draft.body}\n",
                encoding="utf-8",
            )
            log(f"  Saved artifacts to {run_dir.relative_to(RUNS_DIR.parent)}")

            # --- persist ---
            record = ProfessorRecord(
                run_id=run_id,
                prof_slug=prof_slug,
                professor=prof,
                match=match,
                email=email_draft,
                resume_pdf_path=resume_pdf_path_str,
                email_txt_path=str(email_path),
                created_at=datetime.now(),
            )
            insert_professor_record(record)
            success += 1

        except Exception as exc:
            log(f"  ERROR: {exc}")
            failure += 1

        update_run_counts(run_id, success, failure)

    log(f"\nDone. {success} succeeded, {failure} failed.")
    return success, failure


# ---------------------------------------------------------------------------
# Page: Library
# ---------------------------------------------------------------------------

def page_library():
    st.title("Experience Library")

    # Experience blocks
    st.header("Experience Blocks")
    blocks = _load_library()
    if not blocks:
        st.warning(
            f"`experience_library.md` is missing or empty. "
            f"Edit that file to add your experience blocks. "
            f"See `PRD.md` for the format."
        )
    else:
        st.success(f"{len(blocks)} blocks loaded from `experience_library.md`")
        for b in blocks:
            with st.expander(f"{b.title}  ({b.id})"):
                if b.organization:
                    st.write(f"**Organization:** {b.organization}")
                if b.dates:
                    st.write(f"**Dates:** {b.dates}")
                st.write(f"**Tags:** {', '.join(b.tags)}")
                st.write(f"**Summary:** {b.summary}")
                st.write("**Bullets:**")
                for bullet in b.bullets:
                    st.write(f"- {bullet}")

    st.divider()

    # Voice samples
    st.header("Voice Samples")
    voice = _load_voice()
    if not voice:
        st.warning(
            "`voice_samples.md` is missing or empty. "
            "Paste 3-5 real past emails into that file to improve draft quality."
        )
    else:
        st.success("`voice_samples.md` loaded")
        st.text_area("Voice samples (read-only)", value=voice, height=200, disabled=True)

    st.divider()

    # Student info
    st.header("Student Info")
    student = _load_student()
    if not student:
        st.warning(
            "`student.yaml` not found. Copy `student.example.yaml` to `student.yaml` "
            "and fill in your details. This file is gitignored."
        )
    else:
        st.success("`student.yaml` loaded")
        st.json(
            {
                "name": student.name,
                "email": student.email,
                "phone": student.phone,
                "location": student.location,
                "github": student.github,
                "linkedin": student.linkedin,
            }
        )


# ---------------------------------------------------------------------------
# Page: Scrape & Match
# ---------------------------------------------------------------------------

def page_scrape():
    st.title("Scrape & Match")

    input_mode = st.radio(
        "Input mode",
        ["Upload CSV", "Paste URLs"],
        horizontal=True,
    )

    professors: list[ProfessorInput] = []
    csv_filename: str | None = None

    if input_mode == "Upload CSV":
        uploaded = st.file_uploader(
            "CSV with columns: url, name (optional), note (optional)",
            type=["csv"],
        )
        if uploaded:
            csv_filename = uploaded.name
            reader = csv.DictReader(io.StringIO(uploaded.read().decode("utf-8")))
            for row in reader:
                url = row.get("url", "").strip()
                if url:
                    professors.append(
                        ProfessorInput(
                            url=url,
                            name=row.get("name", "").strip() or None,
                            note=row.get("note", "").strip() or None,
                        )
                    )
            st.info(f"{len(professors)} professor(s) loaded from CSV")
    else:
        pasted = st.text_area(
            "Paste up to 20 URLs, one per line",
            height=200,
        )
        if pasted.strip():
            for line in pasted.strip().splitlines():
                url = line.strip()
                if url:
                    professors.append(ProfessorInput(url=url))
            professors = professors[:20]
            st.info(f"{len(professors)} URL(s) entered")

    use_fixtures = st.checkbox(
        "Use sample fixtures instead of live URLs (for testing)",
        value=False,
    )

    if use_fixtures:
        st.info(
            "Fixture mode: the pipeline will use the synthetic HTML files in "
            "`data/sample_faculty_pages/` instead of fetching real URLs."
        )
        fixture_map = _fixture_url_map()
        if not fixture_map:
            st.error("No fixture files found in `data/sample_faculty_pages/`.")
            return
        # in fixture mode we need at least one professor entry to drive the loop
        if not professors:
            professors = [
                ProfessorInput(url=f"fixture://{name}", name=None, note=None)
                for name in fixture_map
            ]
            st.info(f"Using {len(professors)} fixture(s) as input.")

    if not professors:
        st.info("Upload a CSV or paste URLs above, then click Run.")
        return

    run_btn = st.button("Run pipeline", type="primary")

    if run_btn:
        run_id = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        run = Run(
            id=run_id,
            created_at=datetime.now(),
            input_csv_filename=csv_filename,
            professor_count=len(professors),
            success_count=0,
            failure_count=0,
        )
        insert_run(run)

        st.subheader("Progress")
        log_box = st.empty()

        success, failure = run_pipeline(
            professors=professors,
            use_fixtures=use_fixtures,
            run_id=run_id,
            log_placeholder=log_box,
        )

        st.subheader("Summary")
        records = get_professor_records_for_run(run_id)
        if records:
            summary_rows = []
            for rec in records:
                p = rec.professor
                summary_rows.append(
                    {
                        "Name": p.name,
                        "University": p.university or "",
                        "Research areas": ", ".join(p.research_areas[:2]),
                        "Confidence": p.extraction_confidence,
                        "Matched blocks": len(rec.match.top_blocks),
                        "Email words": rec.email.word_count,
                    }
                )
            st.dataframe(summary_rows, use_container_width=True)
        st.success(f"Run `{run_id}` complete: {success} succeeded, {failure} failed.")
        st.info("Go to the Review & Export page to download artifacts.")


# ---------------------------------------------------------------------------
# Page: Review & Export
# ---------------------------------------------------------------------------

def page_review():
    st.title("Review & Export")

    runs = list_runs()
    if not runs:
        st.info("No runs yet. Go to Scrape & Match to start a run.")
        return

    run_options = {
        f"{r.id}  ({r.professor_count} profs, {r.success_count} ok)": r.id
        for r in runs
    }
    selected_label = st.selectbox("Select a run", list(run_options.keys()))
    if not selected_label:
        return

    selected_run_id = run_options[selected_label]
    records = get_professor_records_for_run(selected_run_id)

    if not records:
        st.warning("No professor records found for this run.")
        return

    st.write(f"{len(records)} professor(s) in this run")

    for rec in records:
        p = rec.professor
        with st.expander(f"{p.name}  --  {p.university or 'unknown university'}"):
            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**Title:** {p.title or 'N/A'}")
                st.write(f"**Department:** {p.department or 'N/A'}")
                st.write(f"**Research areas:** {', '.join(p.research_areas)}")
                if p.recent_papers:
                    st.write(f"**Recent papers:** {'; '.join(p.recent_papers)}")
                st.write(f"**Extraction confidence:** {p.extraction_confidence}")
                if p.contact_email:
                    st.write(f"**Contact email:** {p.contact_email}")

                st.write("**Match reasoning:**")
                st.write(rec.match.match_reasoning)
                st.write(f"**Matched blocks:** {', '.join(b.id for b in rec.match.top_blocks)}")

            with col2:
                st.write("**Email draft:**")
                email_body = st.text_area(
                    "Edit before sending (not saved back to DB)",
                    value=f"Subject: {rec.email.subject}\n\n{rec.email.body}",
                    height=220,
                    key=f"email_{rec.prof_slug}",
                )
                st.code(email_body, language=None)
                st.caption(f"{rec.email.word_count} words (original draft)")

                if rec.resume_pdf_path:
                    resume_path = Path(rec.resume_pdf_path)
                    if resume_path.exists():
                        with open(resume_path, "rb") as pdf_f:
                            st.download_button(
                                label="Download Resume PDF",
                                data=pdf_f.read(),
                                file_name=f"resume_{rec.prof_slug}.pdf",
                                mime="application/pdf",
                                key=f"dl_{rec.prof_slug}",
                            )
                    else:
                        st.warning("Resume PDF file missing from disk.")
                else:
                    st.warning("PDF not available -- add student.yaml and re-run.")


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

PAGES = {
    "Library": page_library,
    "Scrape & Match": page_scrape,
    "Review & Export": page_review,
}

with st.sidebar:
    st.title("profreach")
    st.caption("Automated research outreach pipeline")
    st.divider()
    selected_page = st.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")

PAGES[selected_page]()
