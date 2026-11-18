"""Local, file-based project storage for the interactive workbench."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


class LocalProjectStore:
    """Persist models without any cloud service or database server."""

    def __init__(self, root: Path | str = "projects"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def slug(name: str) -> str:
        result = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not result:
            raise ValueError("Project name must contain a letter or number.")
        return result

    def project_dir(self, name: str) -> Path:
        return self.root / self.slug(name)

    def list(self) -> list[str]:
        return sorted(path.name for path in self.root.iterdir() if path.is_dir() and (path / "project.json").is_file())

    def save(self, name: str, wrapper, msx_file: Path | None = None, geopackage: Path | None = None) -> Path:
        directory = self.project_dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        wrapper.save_input_file(directory / "model.inp")
        files = {"inp": "model.inp"}
        for source, key, target in ((msx_file, "msx", "chemistry.msx"), (geopackage, "geopackage", "assets.gpkg")):
            if source is not None and Path(source).is_file():
                shutil.copy2(source, directory / target)
                files[key] = target
        (directory / "project.json").write_text(json.dumps({
            "name": name, "saved_at": datetime.now(timezone.utc).isoformat(), "files": files,
        }, indent=2), encoding="utf-8")
        return directory

    def load(self, name: str) -> dict:
        directory = self.project_dir(name)
        metadata = json.loads((directory / "project.json").read_text(encoding="utf-8"))
        return {key: directory / value for key, value in metadata["files"].items()} | {"name": metadata["name"]}
