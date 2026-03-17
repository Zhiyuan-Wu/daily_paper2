"""Configuration utilities for paper extend metadata module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from service.common.config_loader import DEFAULT_CONFIG_PATH, load_app_config

_DEFAULT_PROMPT = """
你是一个论文元信息抽取器。请根据给定的论文基础信息和论文首页 OCR 文本，返回一个 JSON 对象，不要输出 JSON 之外的任何内容。

请严格使用下面的字段：
{
  "abstract_cn": "将原始英文摘要翻译成中文；如果原始摘要缺失则为空字符串",
  "affliations": ["作者单位列表，去重，使用字符串数组；未知则返回空数组"],
  "keywords": ["论文关键词列表，去重，使用字符串数组；未知则返回空数组"],
  "github_repo": "论文关联的 GitHub 仓库 URL；未知则返回空字符串"
}

要求：
1. `abstract_cn` 优先翻译输入中的 original abstract，而不是凭空生成摘要。
2. `affliations` 仅提取作者单位，不要包含作者姓名。
3. `keywords` 仅返回短语，不要返回长句。
4. `github_repo` 仅返回 GitHub 链接。
5. 如果信息不存在，返回空字符串或空数组，不要返回 null。
""".strip()


def get_paper_extend_metadata_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return ``paper_extend_metadata`` section, with compatibility fallbacks."""
    cfg = load_app_config(config_path)
    section = cfg.get("paper_extend_metadata")
    if section is not None:
        if not isinstance(section, dict):
            raise ValueError("Config section 'paper_extend_metadata' must be a mapping")
        return section

    fetch_cfg = cfg.get("paper_fetch") if isinstance(cfg.get("paper_fetch"), dict) else {}
    db_path = str(fetch_cfg.get("db_path") or "data/papers.db")
    return {
        "db_path": db_path,
        "table_name": "extend_metadata",
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4.1-mini",
            "timeout_seconds": 120,
        },
    }


def get_default_extend_metadata_prompt() -> str:
    return _DEFAULT_PROMPT


def resolve_openai_api_key(
    config_api_key: str | None = None,
    config_path: str | Path | None = None,
) -> str:
    """Resolve API key from explicit config value, then local .env, then environment."""
    if isinstance(config_api_key, str) and config_api_key.strip():
        return config_api_key.strip()

    env_path = _resolve_env_path(config_path)
    env_values = _load_dotenv_file(env_path)
    file_value = env_values.get("OPENAI_API_KEY", "").strip()
    if file_value:
        return file_value

    import os

    return (os.getenv("OPENAI_API_KEY") or "test-key").strip()


def _resolve_env_path(config_path: str | Path | None) -> Path:
    if config_path is None:
        return DEFAULT_CONFIG_PATH.parent / ".env"
    return Path(config_path).resolve().parent / ".env"


def _load_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values
