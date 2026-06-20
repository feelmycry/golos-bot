from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY
from prompts.templates import (
    build_client_prompt,
    build_feedback_prompt,
    build_summary_prompt,
)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client

_OPENING_TRIGGER = "Начни диалог — поздоровайся и кратко озвучь свою задачу (1–2 предложения)."


def _to_claude_messages(messages: list) -> list:
    """
    Convert session messages to Claude API format.
    Client messages → assistant role, employee messages → user role.
    Always prepends a synthetic user trigger so the first turn is 'user'.
    """
    result = [{"role": "user", "content": _OPENING_TRIGGER}]
    for msg in messages:
        role = "assistant" if msg["role"] == "client" else "user"
        result.append({"role": role, "content": msg["content"]})
    return result


async def get_opening_message(profile: dict, stage: str, product: str | None) -> str:
    system = build_client_prompt(profile, stage, product)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": _OPENING_TRIGGER}],
    )
    return response.content[0].text.strip()


async def continue_dialog(
    profile: dict,
    stage: str,
    messages: list,
    product: str | None,
) -> str:
    """
    messages already includes the latest employee message at the end.
    Claude will respond as the client.
    """
    system = build_client_prompt(profile, stage, product)
    claude_msgs = _to_claude_messages(messages)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=350,
        system=system,
        messages=claude_msgs[-22:],
    )
    return response.content[0].text.strip()


async def get_feedback(
    messages: list,
    last_employee: str,
    stage: str,
    product: str | None,
) -> str:
    prompt = build_feedback_prompt(messages, last_employee, stage, product)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def get_session_summary(
    messages: list,
    stage: str,
    product: str | None,
    profile: dict,
) -> str:
    prompt = build_summary_prompt(messages, stage, product, profile)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
