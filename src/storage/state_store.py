from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from src.config import DATA_ROOT, get_project_paths
from src.orchestrator.state import ProjectState
from src.schemas.chapter import DetailOutline
from src.schemas.outline import NovelOutline
from src.schemas.project import ProjectRecord


class StateStore:
    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = data_root or DATA_ROOT

    def initialize_project(self, record: ProjectRecord, state: ProjectState) -> None:
        paths = get_project_paths(record.project_id)
        paths.ensure()
        self.save_project_record(record.project_id, record)
        self.save_state(record.project_id, state)

    def save_project_record(self, project_id: str, record: ProjectRecord) -> None:
        paths = get_project_paths(project_id)
        paths.ensure()
        self._write_json(paths.project_file, record.model_dump(mode="json"))

    def load_project_record(self, project_id: str) -> ProjectRecord:
        data = self._read_json(get_project_paths(project_id).project_file)
        return ProjectRecord.model_validate(data)

    def save_state(self, project_id: str, state: ProjectState) -> None:
        paths = get_project_paths(project_id)
        paths.ensure()
        self._write_json(paths.progress_file, state.model_dump(mode="json"))

    def load_state(self, project_id: str) -> ProjectState:
        data = self._read_json(get_project_paths(project_id).progress_file)
        return ProjectState.model_validate(data)

    def save_outline(self, project_id: str, outline: NovelOutline) -> None:
        paths = get_project_paths(project_id)
        paths.ensure()
        self._write_json(paths.outline_file, outline.model_dump(mode="json"))

    def load_outline(self, project_id: str) -> NovelOutline:
        data = self._read_json(get_project_paths(project_id).outline_file)
        return NovelOutline.model_validate(data)

    def save_detail_outline(self, project_id: str, detail_outline: DetailOutline) -> Path:
        paths = get_project_paths(project_id)
        paths.ensure()
        file_path = paths.detail_outlines_dir / f"{detail_outline.chapter_id:04d}.json"
        self._write_json(file_path, detail_outline.model_dump(mode="json"))
        return file_path

    def load_detail_outline(self, project_id: str, chapter_id: int) -> DetailOutline:
        file_path = get_project_paths(project_id).detail_outlines_dir / f"{chapter_id:04d}.json"
        data = self._read_json(file_path)
        return DetailOutline.model_validate(data)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Missing JSON file: {path}")
        return orjson.loads(path.read_bytes())

