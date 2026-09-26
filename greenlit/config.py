"""Environment-driven configuration for Greenlit."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


_load_dotenv_if_present()


@dataclass(frozen=True)
class GreenlitConfig:
    nebius_api_key: str
    nebius_ai_project: str
    tavily_api_key: str | None

    @classmethod
    def from_env(cls) -> "GreenlitConfig":
        api_key = os.environ.get("NEBIUS_API_KEY")
        project = os.environ.get("NEBIUS_AI_PROJECT")
        if not api_key:
            raise RuntimeError("NEBIUS_API_KEY is not set (see .env.example)")
        if not project:
            raise RuntimeError("NEBIUS_AI_PROJECT is not set (see .env.example)")
        return cls(
            nebius_api_key=api_key,
            nebius_ai_project=project,
            tavily_api_key=os.environ.get("TAVILY_API_KEY") or None,
        )
