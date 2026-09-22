"""Thin wrapper around the Nebius Token Factory OpenAI-compatible inference API.

Model tiering (PLAN uses Nemotron Ultra, EVALUATE uses Nemotron Nano/Super) is
resolved live against GET /v1/models rather than hardcoded: sources disagreed
on exact ID casing/format at build time, and the project's own build prompt
says not to guess model IDs. A mismatch here fails loudly instead of silently
calling the wrong tier.
"""
from __future__ import annotations

from openai import OpenAI

from greenlit.config import GreenlitConfig

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"


class NebiusClient:
    def __init__(self, config: GreenlitConfig):
        self._client = OpenAI(base_url=BASE_URL, api_key=config.nebius_api_key)

    def list_models(self) -> list[str]:
        return [m.id for m in self._client.models.list().data]

    def resolve_model(self, *keywords: str) -> str:
        keywords_lower = [k.lower() for k in keywords if k]
        matches = [
            model_id
            for model_id in self.list_models()
            if all(k in model_id.lower() for k in keywords_lower)
        ]
        if not matches:
            raise ValueError(f"No live model matches keywords {keywords!r}")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous keywords {keywords!r}, matches: {matches}")
        return matches[0]

    def chat(self, model: str, messages: list[dict], **kwargs):
        return self._client.chat.completions.create(model=model, messages=messages, **kwargs)
