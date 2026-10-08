"""Same-origin demo host; the API remains independently usable."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from recheck.api import app  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

static = ROOT / "web_static"
if static.is_dir():
    app.mount("/", StaticFiles(directory=static, html=True), name="demo")
