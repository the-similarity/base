from __future__ import annotations

import json
from pathlib import Path

from the_similarity_data.models import DatasetSpec


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_dataset_config_path() -> Path:
    return repo_root() / "config" / "datasets.json"


def default_manifest_path() -> Path:
    return repo_root() / "manifests" / "catalog.json"


def load_dataset_specs(config_path: Path | None = None) -> list[DatasetSpec]:
    path = config_path or default_dataset_config_path()
    payload = json.loads(path.read_text())
    return [DatasetSpec(**item) for item in payload]
