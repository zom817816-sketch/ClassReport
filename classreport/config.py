from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Paths are always relative to the project directory."""

    root: Path
    report_date: date
    teacher: str = "毛远老师"
    source_data_dir: Path | None = None

    @property
    def data_dir(self) -> Path:
        return self.source_data_dir or self.root / "data"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def packages_dir(self) -> Path:
        return self.output_dir / "packages"

    @property
    def manifests_dir(self) -> Path:
        return self.output_dir / "manifests"
