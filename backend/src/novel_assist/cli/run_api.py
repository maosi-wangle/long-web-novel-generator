from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(
        "novel_assist.api.app:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
