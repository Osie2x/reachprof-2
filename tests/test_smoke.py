"""Smoke tests for the full profreach pipeline.

All LLM calls are monkeypatched -- no network, no real Anthropic calls.
Tests confirm: extraction parses correctly, matching returns ranked blocks,
email draft is 90-110 words and free of banned phrases, resume PDF is written.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from profreach.config import EXPERIENCE_LIBRARY_PATH, FIXTURES_DIR, VOICE_SAMPLES_PATH
from profreach.drafting import draft_email
from profreach.extraction import extract_professor
from profreach.library import parse_library
from profreach.matching import match_blocks
from profreach.models import ExtractedProfessor, ExperienceBlock, StudentInfo
from profreach.resume import render_resume
from profreach.scraping import html_to_clean_text, load_fixture
from profreach.validation import validate_extraction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BANNED_PHRASES = [
    "i hope this email finds you well",
    "i hope you are doing well",
    "i would love the opportunity to",
    "passionate about",
    "thrilled",
    "excited to learn",
    "align with your research",
]


@pytest.fixture
def sample_blocks() -> list[ExperienceBlock]:
    with open(EXPERIENCE_LIBRARY_PATH) as f:
        md = f.read()
    return parse_library(md)


@pytest.fixture
def fake_professor() -> ExtractedProfessor:
    return ExtractedProfessor(
        name="Dr. Jordan Ellis",
        title="Associate Professor",
        university="Ontario Regional University",
        department="Computer Science",
        research_areas=[
            "probabilistic graphical models",
            "graph neural networks for structured prediction",
            "variational inference",
        ],
        recent_papers=[
            "Equivariant Message Passing for Molecular Property Prediction",
            "Scalable Variational Inference for Deep Latent Gaussian Graph Models",
        ],
        contact_email="j.ellis@oru.ca",
        page_url="fixture://university_a_cs.html",
        extraction_confidence="high",
        extraction_notes="Research Interests section and Publications list",
    )


# ---------------------------------------------------------------------------
# Scraping tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", [
    "university_a_cs.html",
    "university_b_math.html",
    "university_c_compbio.html",
    "small_college_cs.html",
])
def test_html_to_clean_text(fixture_name: str):
    html = load_fixture(str(FIXTURES_DIR / fixture_name))
    text = html_to_clean_text(html)
    assert len(text) > 200, f"{fixture_name}: extracted text too short ({len(text)} chars)"
    assert text.strip() != "", f"{fixture_name}: extracted text is empty"


# ---------------------------------------------------------------------------
# Extraction tests (monkeypatched)
# ---------------------------------------------------------------------------

def _fake_extraction_response(name: str = "Dr. Jordan Ellis") -> dict:
    return {
        "name": name,
        "title": "Associate Professor",
        "university": "Ontario Regional University",
        "department": "Computer Science",
        "research_areas": [
            "probabilistic graphical models",
            "graph neural networks for structured prediction",
            "variational inference",
        ],
        "recent_papers": [
            "Equivariant Message Passing for Molecular Property Prediction",
            "Scalable Variational Inference for Deep Latent Gaussian Graph Models",
        ],
        "contact_email": "j.ellis@oru.ca",
        "extraction_confidence": "high",
        "extraction_notes": "Research Interests section",
    }


@pytest.mark.parametrize("fixture_name", [
    "university_a_cs.html",
    "university_b_math.html",
    "university_c_compbio.html",
    "small_college_cs.html",
])
def test_extraction_on_fixtures(fixture_name: str):
    """Extraction returns non-empty research_areas for each fixture."""
    html = load_fixture(str(FIXTURES_DIR / fixture_name))
    page_text = html_to_clean_text(html)

    fake_response = _fake_extraction_response()

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(fake_response))]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("profreach.extraction.anthropic.Anthropic", return_value=mock_client):
        prof = extract_professor(
            page_text=page_text,
            page_url=f"fixture://{fixture_name}",
        )

    assert prof.research_areas, f"{fixture_name}: research_areas is empty"
    assert len(prof.research_areas) >= 1
    assert prof.name


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_validate_clean_extraction(fake_professor: ExtractedProfessor):
    warnings = validate_extraction(fake_professor)
    assert warnings == []


def test_validate_catches_empty_research_areas(fake_professor: ExtractedProfessor):
    bad = fake_professor.model_copy(update={"research_areas": []})
    warnings = validate_extraction(bad)
    assert any("research areas" in w.lower() for w in warnings)


def test_validate_catches_bad_email(fake_professor: ExtractedProfessor):
    bad = fake_professor.model_copy(update={"contact_email": "not-an-email"})
    warnings = validate_extraction(bad)
    assert any("email" in w.lower() for w in warnings)


def test_validate_catches_low_confidence(fake_professor: ExtractedProfessor):
    bad = fake_professor.model_copy(update={"extraction_confidence": "low"})
    warnings = validate_extraction(bad)
    assert any("confidence" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Library parser tests
# ---------------------------------------------------------------------------

def test_parse_library_returns_blocks(sample_blocks):
    assert len(sample_blocks) > 0


def test_parse_library_block_fields(sample_blocks):
    for b in sample_blocks:
        assert b.id
        assert b.title
        assert isinstance(b.bullets, list)
        assert isinstance(b.tags, list)
        assert isinstance(b.summary, str)


# ---------------------------------------------------------------------------
# Matching tests (monkeypatched)
# ---------------------------------------------------------------------------

def test_matching_returns_ranked_blocks(fake_professor: ExtractedProfessor, sample_blocks):
    fake_match_response = {
        "top_block_ids": [sample_blocks[0].id, sample_blocks[1].id],
        "match_reasoning": (
            "The professor works on probabilistic graphical models. "
            f"{sample_blocks[0].id} is directly relevant due to its ML tags. "
            f"{sample_blocks[1].id} provides supporting analytical background."
        ),
    }

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(fake_match_response))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("profreach.matching.anthropic.Anthropic", return_value=mock_client):
        result = match_blocks(professor=fake_professor, blocks=sample_blocks)

    assert len(result.top_blocks) >= 1
    assert result.match_reasoning
    # reasoning should name a research area
    assert any(
        area.lower() in result.match_reasoning.lower()
        for area in fake_professor.research_areas
    )


# ---------------------------------------------------------------------------
# Drafting tests (monkeypatched)
# ---------------------------------------------------------------------------

def _fake_email_body() -> str:
    return (
        "Hi Dr. Ellis, I came across your recent paper on equivariant message passing for molecular "
        "property prediction and had a quick question about how you handled the uncertainty "
        "quantification side of things. I'm a first-year CS student at Wilfrid Laurier "
        "and I've been working on a small graph-structured prediction problem this term "
        "where I'm running into similar issues. My background is Python and linear algebra, "
        "and I've been reading into probabilistic graphical models on the side. Would you "
        "have 15 minutes in the next couple of weeks to chat? Thanks, Osie."
    )


def test_email_word_count(fake_professor: ExtractedProfessor, sample_blocks):
    body = _fake_email_body()
    word_count = len(body.split())
    assert 90 <= word_count <= 110, f"Word count {word_count} outside 90-110"


def test_email_no_banned_phrases(fake_professor: ExtractedProfessor, sample_blocks):
    body = _fake_email_body().lower()
    for phrase in BANNED_PHRASES:
        assert phrase not in body, f"Banned phrase found: {phrase!r}"


def test_draft_email_module(fake_professor: ExtractedProfessor, sample_blocks):
    """Full drafting module with monkeypatched LLM."""
    body = _fake_email_body()
    fake_draft_response = {
        "subject": "question about equivariant message passing",
        "body": body,
    }

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(fake_draft_response))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("profreach.drafting.anthropic.Anthropic", return_value=mock_client):
        draft = draft_email(
            professor=fake_professor,
            top_blocks=sample_blocks[:2],
            voice_samples_text="Hey Prof X, quick question about your paper...",
            student_name="Osie",
            student_context="First-year BBA/CS, Wilfrid Laurier University",
        )

    assert 90 <= draft.word_count <= 110, f"Word count {draft.word_count} outside 90-110"
    body_lower = draft.body.lower()
    for phrase in BANNED_PHRASES:
        assert phrase not in body_lower, f"Banned phrase in draft: {phrase!r}"
    # must end with first name only (no comma check -- just check name present near end)
    assert "osie" in draft.body.lower()[-30:]


# ---------------------------------------------------------------------------
# Resume tests
# ---------------------------------------------------------------------------

def test_resume_pdf_is_written(sample_blocks):
    student = StudentInfo(
        name="Osie Igbinoba",
        email="test@example.com",
        phone="+1 (xxx) xxx-xxxx",
        location="Waterloo, ON",
        github="github.com/Osie2x",
        linkedin="linkedin.com/in/osie",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "resume.pdf"
        render_resume(student=student, ordered_blocks=sample_blocks, output_path=out_path)
        assert out_path.exists(), "resume.pdf was not created"
        assert out_path.stat().st_size > 5000, "resume.pdf is suspiciously small"


# ---------------------------------------------------------------------------
# End-to-end pipeline test (all monkeypatched, no network, no real LLM)
# ---------------------------------------------------------------------------

def test_full_pipeline_end_to_end(tmp_path, sample_blocks):
    """Full pipeline: fixture -> extract -> match -> draft -> PDF."""
    from profreach.db import init_db, insert_run, insert_professor_record, get_professor_records_for_run
    from profreach.models import ProfessorInput, ProfessorRecord, Run

    # use a temp DB
    import profreach.db as db_module
    import profreach.config as config_module

    original_db = config_module.DB_PATH
    original_runs = config_module.RUNS_DIR
    config_module.DB_PATH = tmp_path / "test.db"
    config_module.RUNS_DIR = tmp_path / "runs"
    config_module.RUNS_DIR.mkdir()

    try:
        db_module.DB_PATH = config_module.DB_PATH
        init_db()

        fixture_name = "university_a_cs.html"
        html = load_fixture(str(FIXTURES_DIR / fixture_name))
        page_text = html_to_clean_text(html)

        # monkeypatched extraction
        fake_ext = _fake_extraction_response()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(fake_ext))]
        mock_cl = MagicMock()
        mock_cl.messages.create.return_value = mock_msg

        with patch("profreach.extraction.anthropic.Anthropic", return_value=mock_cl):
            prof = extract_professor(page_text, f"fixture://{fixture_name}")

        assert prof.research_areas

        # monkeypatched matching
        fake_match = {
            "top_block_ids": [sample_blocks[0].id],
            "match_reasoning": f"Block {sample_blocks[0].id} matches probabilistic graphical models.",
        }
        mock_msg2 = MagicMock()
        mock_msg2.content = [MagicMock(text=json.dumps(fake_match))]
        mock_cl2 = MagicMock()
        mock_cl2.messages.create.return_value = mock_msg2

        with patch("profreach.matching.anthropic.Anthropic", return_value=mock_cl2):
            match = match_blocks(professor=prof, blocks=sample_blocks)

        assert len(match.top_blocks) >= 1

        # monkeypatched drafting
        body = _fake_email_body()
        fake_draft = {"subject": "question about your research", "body": body}
        mock_msg3 = MagicMock()
        mock_msg3.content = [MagicMock(text=json.dumps(fake_draft))]
        mock_cl3 = MagicMock()
        mock_cl3.messages.create.return_value = mock_msg3

        with open(VOICE_SAMPLES_PATH) as f:
            voice = f.read()

        with patch("profreach.drafting.anthropic.Anthropic", return_value=mock_cl3):
            email_draft = draft_email(
                professor=prof,
                top_blocks=match.top_blocks,
                voice_samples_text=voice,
                student_name="Osie",
                student_context="First-year BBA/CS, Wilfrid Laurier University",
            )

        assert 90 <= email_draft.word_count <= 110

        # render PDF
        student = StudentInfo(
            name="Osie Igbinoba",
            email="test@example.com",
            phone="+1 (xxx) xxx-xxxx",
            location="Waterloo, ON",
        )
        run_id = "run_test"
        prof_slug = "dr-jordan-ellis"
        run_dir = config_module.RUNS_DIR / run_id / prof_slug
        run_dir.mkdir(parents=True)
        resume_path = run_dir / "resume.pdf"
        email_path = run_dir / "email.txt"

        render_resume(student=student, ordered_blocks=match.top_blocks, output_path=resume_path)
        email_path.write_text(f"Subject: {email_draft.subject}\n\n{email_draft.body}")

        assert resume_path.exists(), "resume.pdf not created"
        assert resume_path.stat().st_size > 5000, "resume.pdf too small"
        assert email_path.exists(), "email.txt not created"

        # check email txt word count
        email_txt_body = email_path.read_text().split("\n\n", 1)[1].strip()
        wc = len(email_txt_body.split())
        assert 90 <= wc <= 110, f"email.txt body word count {wc} outside 90-110"

        # persist and retrieve
        run = Run(
            id=run_id,
            created_at=datetime.now(),
            input_csv_filename=None,
            professor_count=1,
            success_count=1,
            failure_count=0,
        )
        insert_run(run)

        record = ProfessorRecord(
            run_id=run_id,
            prof_slug=prof_slug,
            professor=prof,
            match=match,
            email=email_draft,
            resume_pdf_path=str(resume_path),
            email_txt_path=str(email_path),
            created_at=datetime.now(),
        )
        insert_professor_record(record)

        retrieved = get_professor_records_for_run(run_id)
        assert len(retrieved) == 1
        assert retrieved[0].prof_slug == prof_slug

        print("Full pipeline test passed.")

    finally:
        config_module.DB_PATH = original_db
        config_module.RUNS_DIR = original_runs
        db_module.DB_PATH = original_db
