"""Minimal OpenAI-compatible chat client with model fallback.

Pointed at Open WebUI (`http://<host>:30070/api`), the model name picks the
backend: a llama-server preset like `chat`, or an OpenRouter model id. Models
are tried in order, so a local model can come first with a hosted one as the
fallback for when the desktop is off.

A model is a name, or `{name: ..., extra: {...}}` where `extra` is merged into
the request body, e.g. `{chat_template_kwargs: {enable_thinking: false}}` to
stop a local reasoning model thinking for 15k tokens about which story to pick.
"""

from __future__ import annotations

import json
import logging
import re
import time

import requests

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, base_url: str, api_key: str, models: list, timeout: int = 180, max_tokens: int = 4096):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.models = [m if isinstance(m, dict) else {"name": m} for m in models]
        self.timeout = timeout
        self.max_tokens = max_tokens

    @property
    def enabled(self) -> bool:
        return bool(self.models and self.url.startswith("http"))

    def chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        if not self.enabled:
            raise LLMError("no LLM configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        errors = []
        for m in self.models:
            model = m["name"]
            body = {
                "model": model,
                "stream": True,
                "temperature": temperature,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **(m.get("extra") or {}),
            }
            try:
                content = self._stream(headers, body)
                if content.strip():
                    log.info("llm: answered by %s", model)
                    return content
                errors.append(f"{model}: empty reply")
            except (requests.RequestException, KeyError, IndexError, ValueError, LLMError) as e:
                errors.append(f"{model}: {e}")
                log.warning("llm: %s failed (%s), trying next model", model, e)
        raise LLMError("; ".join(errors))

    def _stream(self, headers: dict, body: dict) -> str:
        """Stream the reply so `timeout` bounds the whole call, not just each read."""
        deadline = time.monotonic() + self.timeout
        parts: list[str] = []
        with requests.post(self.url, headers=headers, json=body, stream=True, timeout=(10, 120)) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if time.monotonic() > deadline:
                    raise LLMError(f"no complete reply within {self.timeout}s")
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    raise LLMError(str(chunk["error"]))
                choices = chunk.get("choices") or []
                if choices:
                    parts.append((choices[0].get("delta") or {}).get("content") or "")
        return "".join(parts)

    def chat_json(self, system: str, user: str) -> dict:
        return parse_json(self.chat(system, user))


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (fences, thinking, chatter)."""
    text = _THINK.sub("", text)
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError(f"no JSON object in reply: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"bad JSON in reply: {e}") from e
