"""Shared LLM helper (named news_llm to avoid clashing with other packages called `llm`). Every stage (rank, script, ...) talks to the model through here.

- call_llm(): the ONLY place that knows about the provider (Gemini). Swap providers here.
- generate_json(): ask for JSON, validate with Pydantic, feed errors back and retry.
"""
from __future__ import annotations

import json
import logging
import re
import time

from google import genai
from google.genai import errors, types

import config

log = logging.getLogger(__name__)

_client = None
_skip_models: set[str] = set()  # models that failed earlier in this run


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY from the environment
    return _client


def call_llm(prompt: str, system: str) -> str:
    """Call Gemini. Free tier is often busy: retry, then fall back to the next model."""
    all_models = [config.MODEL] + [m for m in config.FALLBACK_MODELS if m != config.MODEL]
    # Skip models that already failed earlier in this run, so we don't wait through
    # the same 503 retries on every call. If everything failed, try them all again.
    models = [m for m in all_models if m not in _skip_models] or all_models
    last_exc = None
    for model in models:
        for attempt in range(3):
            try:
                resp = _get_client().models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                )
                return resp.text or ""
            except errors.APIError as exc:
                last_exc = exc
                if exc.code in (429, 503):
                    if attempt < 2:
                        wait = 10 * (attempt + 1)
                        log.warning("%s: Gemini %s, retrying in %ds", model, exc.code, wait)
                        time.sleep(wait)
                        continue
                    log.warning("%s still unavailable, skipping it for the rest of this run", model)
                    _skip_models.add(model)
                    break
                if exc.code == 404:
                    log.warning("Model %s not found, trying next model", model)
                    _skip_models.add(model)
                    break
                raise
    raise RuntimeError(f"All Gemini models failed. Last error: {last_exc}")


def _extract_json(text: str) -> str:
    text = text.strip()
    return re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()


def generate_json(
    prompt: str,
    system: str,
    model_cls,
    *,
    list_key: str | None = None,
    validate=None,
    retries: int = 4,
):
    """Return a validated `model_cls` instance.

    list_key: if the model returns a bare list, wrap it as {list_key: [...]}.
    validate: optional function(obj) that raises ValueError for business-rule failures
              (e.g. "too many words"). The error text is sent back to the model.
    """
    current_prompt = prompt
    last_error = ""
    for attempt in range(1, retries + 1):
        raw = call_llm(current_prompt, system)
        try:
            data = json.loads(_extract_json(raw))
            if isinstance(data, list) and list_key:
                data = {list_key: data}
            obj = model_cls.model_validate(data)
            if validate:
                validate(obj)
            return obj
        except ValueError as exc:  # JSONDecodeError and pydantic ValidationError are ValueErrors
            last_error = str(exc).splitlines()[0][:300] if str(exc) else repr(exc)
            log.warning("Attempt %d invalid: %s", attempt, last_error)
            current_prompt = (
                f"{prompt}\n\nYour previous reply was invalid ({last_error}). "
                "Return corrected JSON only."
            )
    raise RuntimeError(f"LLM output failed validation after {retries} attempts: {last_error}")
