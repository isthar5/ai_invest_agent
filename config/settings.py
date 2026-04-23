from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _env_path(name: str, default: Path, project_root: Path) -> Path:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    return p


@dataclass(frozen=True)
class Settings:
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = _env_int("QDRANT_PORT", 6333)
    COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "finance_reports")

    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    RERANKER_DEVICE: str = os.getenv("RERANKER_DEVICE", "cpu")
    ENABLE_MMR: bool = _env_bool("ENABLE_MMR", True)
    MMR_LAMBDA: float = _env_float("MMR_LAMBDA", 0.7)

    # Memory 配置
    MEMORY_REDIS_URL: str = os.getenv("MEMORY_REDIS_URL", "redis://localhost:6379")
    MEMORY_SHORT_TERM_TTL: int = _env_int("MEMORY_SHORT_TERM_TTL", 3600)
    MEMORY_LONG_TERM_TTL: int = _env_int("MEMORY_LONG_TERM_TTL", 2592000)  # 30天
    MEMORY_SHORT_TERM_MAX_LEN: int = _env_int("MEMORY_SHORT_TERM_MAX_LEN", 20)

    PDF_DIR: Path = field(init=False)
    MARKDOWN_DIR: Path = field(init=False)
    REPORT_PATH: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "PDF_DIR",
            _env_path("PDF_DIR", self.PROJECT_ROOT / "data" / "pdfs", self.PROJECT_ROOT),
        )
        object.__setattr__(
            self,
            "MARKDOWN_DIR",
            _env_path("MARKDOWN_DIR", self.PROJECT_ROOT / "data" / "markdowns", self.PROJECT_ROOT),
        )
        object.__setattr__(
            self,
            "REPORT_PATH",
            _env_path("REPORT_PATH", self.PROJECT_ROOT / "reports", self.PROJECT_ROOT),
        )


settings = Settings()
