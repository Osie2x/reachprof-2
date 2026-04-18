from __future__ import annotations
import sqlite3
import json
from datetime import datetime
from .config import DB_PATH
from .models import Run, ProfessorRecord, ExtractedProfessor, MatchResult, EmailDraft


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                input_csv_filename TEXT,
                professor_count INTEGER NOT NULL,
                success_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS professor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                prof_slug TEXT NOT NULL,
                professor_json TEXT NOT NULL,
                match_json TEXT NOT NULL,
                email_json TEXT NOT NULL,
                resume_pdf_path TEXT NOT NULL,
                email_txt_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );
        """)


def insert_run(run: Run) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO runs (id, created_at, input_csv_filename, professor_count, success_count, failure_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run.id,
                run.created_at.isoformat(),
                run.input_csv_filename,
                run.professor_count,
                run.success_count,
                run.failure_count,
            ),
        )


def update_run_counts(run_id: str, success_count: int, failure_count: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE runs SET success_count = ?, failure_count = ? WHERE id = ?",
            (success_count, failure_count, run_id),
        )


def insert_professor_record(record: ProfessorRecord) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO professor_records
               (run_id, prof_slug, professor_json, match_json, email_json, resume_pdf_path, email_txt_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.run_id,
                record.prof_slug,
                record.professor.model_dump_json(),
                record.match.model_dump_json(),
                record.email.model_dump_json(),
                record.resume_pdf_path,
                record.email_txt_path,
                record.created_at.isoformat(),
            ),
        )


def list_runs() -> list[Run]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        result.append(
            Run(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                input_csv_filename=row["input_csv_filename"],
                professor_count=row["professor_count"],
                success_count=row["success_count"],
                failure_count=row["failure_count"],
            )
        )
    return result


def get_professor_records_for_run(run_id: str) -> list[ProfessorRecord]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM professor_records WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()

    result = []
    for row in rows:
        professor = ExtractedProfessor.model_validate_json(row["professor_json"])
        match = MatchResult.model_validate_json(row["match_json"])
        email = EmailDraft.model_validate_json(row["email_json"])
        result.append(
            ProfessorRecord(
                run_id=row["run_id"],
                prof_slug=row["prof_slug"],
                professor=professor,
                match=match,
                email=email,
                resume_pdf_path=row["resume_pdf_path"],
                email_txt_path=row["email_txt_path"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        )
    return result
