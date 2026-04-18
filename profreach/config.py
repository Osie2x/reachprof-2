import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
DB_PATH = DATA_DIR / "profreach.db"
FIXTURES_DIR = DATA_DIR / "sample_faculty_pages"
EXPERIENCE_LIBRARY_PATH = BASE_DIR / "experience_library.md"
VOICE_SAMPLES_PATH = BASE_DIR / "voice_samples.md"
STUDENT_YAML_PATH = BASE_DIR / "student.yaml"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"

RUNS_DIR.mkdir(parents=True, exist_ok=True)
