"""Local, file-based project storage for the interactive workbench."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


class LocalProjectStore:
    """Persist models without any cloud service or database server.

    A project directory holds ``model.inp`` plus optional ``chemistry.msx``,
    ``assets.gpkg``, saved scenario results (``scenarios/*.npz``) and UI
    metadata such as the coordinate reference system.
    """

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

    def save(self, name: str, wrapper, msx_file: Path | None = None, geopackage: Path | None = None,
             metadata: dict | None = None, scenarios: list | None = None) -> Path:
        directory = self.project_dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        wrapper.save_input_file(directory / "model.inp")
        files = {"inp": "model.inp"}
        for source, key, target in ((msx_file, "msx", "chemistry.msx"), (geopackage, "geopackage", "assets.gpkg")):
            if source is not None and Path(source).is_file():
                if Path(source).resolve() != (directory / target).resolve():
                    shutil.copy2(source, directory / target)
                files[key] = target
        saved_scenarios = []
        if scenarios:
            folder = directory / "scenarios"
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir()
            for k, scenario in enumerate(scenarios):
                filename = f"{k:02d}-{self.slug(scenario.name)}.npz"
                scenario.results.save(folder / filename)
                saved_scenarios.append({"name": scenario.name, "settings": scenario.settings,
                                        "note": scenario.note, "file": f"scenarios/{filename}"})
        report = getattr(wrapper, "get_conversion_report", lambda: None)()
        if report:
            (directory / "conversion-report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            files["conversion_report"] = "conversion-report.json"
        (directory / "project.json").write_text(json.dumps({
            "name": name, "saved_at": datetime.now(timezone.utc).isoformat(), "files": files,
            "workbench": metadata or {}, "scenarios": saved_scenarios,
        }, indent=2), encoding="utf-8")
        return directory

    def load(self, name: str) -> dict:
        directory = self.project_dir(name)
        metadata = json.loads((directory / "project.json").read_text(encoding="utf-8"))
        out = {key: directory / value for key, value in metadata["files"].items()} | {"name": metadata["name"]}
        out["workbench"] = metadata.get("workbench", {})
        out["scenarios"] = [dict(s, file=directory / s["file"]) for s in metadata.get("scenarios", [])]
        return out
