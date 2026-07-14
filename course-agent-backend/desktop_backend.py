"""Desktop entry point used by the bundled Electron application."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def prepare_runtime() -> None:
    env_path = os.getenv("COURSE_AGENT_ENV_PATH")
    if env_path and Path(env_path).is_file():
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(override=False)

    data_dir = Path(
        os.getenv("COURSE_AGENT_DATA_DIR", Path.home() / ".course-study-desk")
    ).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    os.environ.setdefault("CHROMA_PATH", str(data_dir / "chroma_db"))
    os.chdir(data_dir)


def main() -> None:
    prepare_runtime()

    import uvicorn
    from app.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("COURSE_AGENT_PORT", "8000")),
        workers=1,
        access_log=False,
        log_level=os.getenv("COURSE_AGENT_LOG_LEVEL", "warning"),
    )


if __name__ == "__main__":
    main()
