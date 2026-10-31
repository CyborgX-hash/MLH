"""Provider-agnostic AI client over the OpenAI-compatible chat and embeddings API.

The model only ever returns *candidate* output validated against a Pydantic schema. Nothing it returns is
written to the database without backend validation.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)
THINK = re.compile(r"<think>.*?</think>", re.S)  # Qwen3 reasoning traces


class AIError(Exception):
    status = 502


class ModelUnavailable(AIError):
    status = 503


class AITimeout(AIError):
    status = 504


class AIRateLimited(AIError):
    status = 429


class InvalidModelOutput(AIError):
    """Invalid JSON or missing/invalid fields, after one corrective retry."""

    status = 502


class ContextTooLong(AIError):
    status = 413


def _extract_json(text: str) -> Any:
    text = THINK.sub("", text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


class AIClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        embed_model: Optional[str] = None,
        provider: str = "ollama",
        timeout: float = 180.0,
        transport: Optional[httpx.BaseTransport] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        self.provider, self.model, self.embed_model = provider, model, embed_model or None
        # Provider-specific chat options (e.g. OpenRouter "reasoning"); never overrides the fields set below.
        self.extra_body = dict(extra_body or {})
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport)

    @classmethod
    def from_settings(cls, s: Settings) -> "AIClient":
        return cls(s.ai_base_url, s.ai_model, s.ai_api_key, s.ai_embed_model, s.ai_provider, s.ai_timeout,
                   extra_body=s.ai_extra_body)

    def close(self) -> None:
        self._http.close()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self._http.post(path, json=payload)
        except httpx.TimeoutException:
            raise AITimeout(f"The model at {self.provider} did not answer in time.") from None
        except httpx.TransportError:
            raise ModelUnavailable(f"Cannot reach the AI provider ({self.provider}).") from None
        if resp.status_code == 429:
            raise AIRateLimited("The AI provider is rate limiting requests.")
        body = resp.text.lower()
        if resp.status_code == 404 or "not found" in body and "model" in body:
            raise ModelUnavailable(f"Model '{payload.get('model')}' is not available at {self.provider}.")
        if resp.status_code in (400, 413) and ("context" in body or "too long" in body or "maximum" in body):
            raise ContextTooLong("The retrieved context is too long for the model.")
        if resp.status_code >= 500:
            raise ModelUnavailable(f"The AI provider returned {resp.status_code}.")
        if resp.status_code >= 400:
            raise AIError(f"The AI provider rejected the request ({resp.status_code}).")
        return resp.json()

    def chat_json(self, messages: List[Dict[str, str]], schema: Type[T], max_tokens: int = 1200) -> T:
        """Ask for JSON matching `schema`; one corrective retry on invalid output."""
        convo = list(messages)
        last_error = ""
        for attempt in range(2):
            data = self._post("/chat/completions", {
                **self.extra_body,
                "model": self.model, "messages": convo, "temperature": 0, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            })
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                raise InvalidModelOutput("The AI provider returned an unexpected response shape.") from None
            if data["choices"][0].get("finish_reason") == "length" and attempt == 1:
                raise ContextTooLong("The model ran out of tokens before finishing its answer.")
            try:
                return schema.model_validate(_extract_json(content))
            except (json.JSONDecodeError, ValueError, ValidationError) as exc:
                last_error = str(exc).splitlines()[0][:300]
                convo = messages + [
                    {"role": "assistant", "content": content[:2000]},
                    {"role": "user", "content": f"That was not valid JSON for the required schema ({last_error}). "
                                                "Reply with only the JSON object."},
                ]
        raise InvalidModelOutput(f"The model did not return valid structured output: {last_error}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.embed_model:
            raise ModelUnavailable("No embedding model is configured (AI_EMBED_MODEL).")
        data = self._post("/embeddings", {"model": self.embed_model, "input": texts})
        try:
            return [item["embedding"] for item in sorted(data["data"], key=lambda d: d.get("index", 0))]
        except (KeyError, TypeError):
            raise InvalidModelOutput("The embedding response had an unexpected shape.") from None
