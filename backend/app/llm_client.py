import json

from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .database import SessionLocal
from .models import LlmCallLog

# Approx USD per 1M tokens. Update if pricing changes.
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


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

    usage = response.usage
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

    return json.loads(response.choices[0].message.content)
