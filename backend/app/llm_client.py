import json

from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .database import SessionLocal
from .models import LlmCallLog

# Approx USD per 1M tokens. Update if pricing changes. Search-preview models
# also carry a separate per-call web-search fee not reflected here — token
# cost logged is a lower bound, not the exact bill.
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-5-search-api": {"input": 0.15, "output": 0.60},  # placeholder, unverified — check actual pricing
}

# gpt-4o-mini-search-preview was shut down 2026-07-23; gpt-5-search-api is its successor.
SEARCH_MODEL = "gpt-5-search-api"

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _log_call(model: str, usage, purpose: str, source_script: str):
    prompt_tokens = usage.prompt_tokens if usage else None
    completion_tokens = usage.completion_tokens if usage else None
    total_tokens = usage.total_tokens if usage else None
    price = PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = None
    if prompt_tokens is not None and completion_tokens is not None:
        cost = (prompt_tokens / 1_000_000) * price["input"] + (completion_tokens / 1_000_000) * price["output"]

    session = SessionLocal()
    try:
        session.add(
            LlmCallLog(
                source_script=source_script,
                purpose=purpose,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
            )
        )
        session.commit()
    finally:
        session.close()


def call_structured(prompt: str, schema: dict, purpose: str, source_script: str, model: str = None) -> dict:
    model = model or OPENAI_MODEL
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": schema, "strict": True},
        },
    )
    _log_call(model, response.usage, purpose, source_script)
    return json.loads(response.choices[0].message.content)


def call_with_web_search(prompt: str, purpose: str, source_script: str) -> str:
    """Real web search, not just the model's training data — used to research
    a state's official terminology/authority/URL before ever opening a browser.
    Returns raw text; any URL in it must still be live-verified before use,
    since even search-grounded answers can misstate an exact path."""
    client = get_client()
    response = client.chat.completions.create(
        model=SEARCH_MODEL,
        web_search_options={},
        messages=[{"role": "user", "content": prompt}],
    )
    _log_call(SEARCH_MODEL, response.usage, purpose, source_script)
    return response.choices[0].message.content
