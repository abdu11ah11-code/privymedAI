"""Typed project configuration loaded from YAML files in ``configs/``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# NumPy's legacy seeding accepts only 32-bit unsigned seeds.
MAX_SEED = 2**32 - 1


def find_repo_root(start: Path | None = None) -> Path:
    """Return the nearest ancestor directory containing ``pyproject.toml``."""
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError(f"no pyproject.toml found above {here}")


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path = Path("data")
    models_dir: Path = Path("models")
    reports_dir: Path = Path("reports")

    def resolved(self, root: Path) -> PathsConfig:
        """Make relative paths absolute against ``root`` (the repository root)."""
        return PathsConfig(
            data_dir=root / self.data_dir,
            models_dir=root / self.models_dir,
            reports_dir=root / self.reports_dir,
        )


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=42, ge=0, le=MAX_SEED)
    log_level: LogLevel = "INFO"
    paths: PathsConfig = Field(default_factory=PathsConfig)


def load_config(path: Path) -> ProjectConfig:
    """Load and validate a YAML config. Unknown keys are rejected.

    Relative paths are resolved against the repository root containing the
    config file, so scripts behave identically from any working directory.
    """
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    cfg = ProjectConfig.model_validate(raw)
    root = find_repo_root(path.parent)
    return cfg.model_copy(update={"paths": cfg.paths.resolved(root)})
