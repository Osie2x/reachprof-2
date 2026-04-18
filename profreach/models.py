from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class ProfessorInput(BaseModel):
    """Row from the user's CSV."""
    url: str
    name: Optional[str] = None
    note: Optional[str] = None


class ExtractedProfessor(BaseModel):
    """LLM-extracted data from a faculty page."""
    name: str
    title: Optional[str] = None
    university: Optional[str] = None
    department: Optional[str] = None
    research_areas: list[str] = Field(default_factory=list)
    recent_papers: list[str] = Field(default_factory=list)
    contact_email: Optional[str] = None
    page_url: str
    extraction_confidence: Literal["high", "medium", "low"]
    extraction_notes: str


class ExperienceBlock(BaseModel):
    """A single experience entry from experience_library.md."""
    id: str
    title: str
    organization: Optional[str] = None
    dates: Optional[str] = None
    bullets: list[str]
    tags: list[str]
    summary: str


class MatchResult(BaseModel):
    professor: ExtractedProfessor
    top_blocks: list["ExperienceBlock"]
    match_reasoning: str


class EmailDraft(BaseModel):
    subject: str
    body: str
    word_count: int


class ProfessorRecord(BaseModel):
    """One row in the output for one professor in a run."""
    run_id: str
    prof_slug: str
    professor: ExtractedProfessor
    match: MatchResult
    email: EmailDraft
    resume_pdf_path: str
    email_txt_path: str
    created_at: datetime


class Run(BaseModel):
    id: str
    created_at: datetime
    input_csv_filename: Optional[str]
    professor_count: int
    success_count: int
    failure_count: int
