import re

from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY
from prompts.templates import (
    build_client_prompt,
    build_feedback_prompt,
    build_hint_prompt,
    build_mid_feedback_prompt,
    build_summary_prompt,
    STAGE_OPENING_TRIGGERS,
)

_client: AsyncAnthropic | None = None


def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\*([^\s*][^*\n]*?)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text


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


async def get_opening_message(
    profile: dict,
    stage: str,
    product: str | None,
    difficulty: str = "medium",
    mode: str = "full",
    hidden_product: str | None = None,
    objection_text: str | None = None,
) -> str:
    system = build_client_prompt(profile, stage, product, difficulty, mode, hidden_product, objection_text)
    if mode == "objection" and objection_text:
        trigger = f"Открой диалог — произнеси своё возражение: «{objection_text}»"
    else:
        trigger = STAGE_OPENING_TRIGGERS.get(stage, _OPENING_TRIGGER)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": trigger}],
    )
    return response.content[0].text.strip()


async def continue_dialog(
    profile: dict,
    stage: str,
    messages: list,
    product: str | None,
    difficulty: str = "medium",
    mode: str = "full",
    hidden_product: str | None = None,
    objection_text: str | None = None,
) -> str:
    system = build_client_prompt(profile, stage, product, difficulty, mode, hidden_product, objection_text)
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
    mode: str = "full",
    hidden_product: str | None = None,
) -> str:
    prompt = build_feedback_prompt(messages, last_employee, stage, product, mode, hidden_product)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _strip_markdown(response.content[0].text.strip())


async def get_hint(
    messages: list,
    stage: str,
    product: str | None,
    mode: str = "full",
    hidden_product: str | None = None,
) -> str:
    prompt = build_hint_prompt(messages, stage, product, mode, hidden_product)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _strip_markdown(response.content[0].text.strip())


async def get_mid_feedback(
    messages: list,
    stage: str,
    product: str | None,
    profile: dict,
    mode: str = "full",
    hidden_product: str | None = None,
) -> str:
    prompt = build_mid_feedback_prompt(messages, stage, product, profile, mode, hidden_product)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return _strip_markdown(response.content[0].text.strip())


async def get_session_summary(
    messages: list,
    stage: str,
    product: str | None,
    profile: dict,
    mode: str = "full",
    hidden_product: str | None = None,
) -> str:
    prompt = build_summary_prompt(messages, stage, product, profile, mode, hidden_product)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return _strip_markdown(response.content[0].text.strip())


async def analyze_news_impact(news_text: str, product_id: str) -> str:
    from prompts.news_prompts import build_news_analysis_prompt
    prompt = build_news_analysis_prompt(news_text, product_id)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def analyze_stock(ticker: str, company_name: str, data: dict) -> str:
    """AI investment analysis based on collected market data."""
    sections = []

    price_info = data.get("price") or {}
    if price_info:
        price = price_info.get("price")
        change = price_info.get("change_pct")
        mcap = price_info.get("market_cap")
        line = f"Текущая цена: {price} ₽"
        if change is not None:
            line += f" ({'+' if float(change) >= 0 else ''}{change}%)"
        if mcap:
            line += f", капитализация: {mcap:,.0f} ₽"
        sections.append(line)

    mult = data.get("multipliers") or {}
    if mult:
        m_lines = []
        labels = {"p_e": "P/E", "p_s": "P/S", "ev_ebitda": "EV/EBITDA",
                  "p_bv": "P/BV", "roe": "ROE", "debt_ebitda": "Долг/EBITDA"}
        for k, label in labels.items():
            if mult.get(k):
                m_lines.append(f"{label}={mult[k]}")
        if m_lines:
            sections.append("Мультипликаторы: " + ", ".join(m_lines))

    fin = data.get("financials") or {}
    if fin and fin.get("years") and fin.get("metrics"):
        years = fin["years"]
        metrics = fin["metrics"]
        fin_lines = [f"Годы: {', '.join(years)}"]
        metric_labels = {"revenue": "Выручка", "ebitda": "EBITDA",
                         "net_profit": "Чист.прибыль", "net_debt": "Чист.долг"}
        for key, label in metric_labels.items():
            vals = metrics.get(key, [])
            if vals:
                fin_lines.append(f"{label}: {', '.join(str(v or '—') for v in vals)} млрд ₽")
        sections.append("\n".join(fin_lines))

    divs_moex = data.get("dividends_moex") or []
    if divs_moex:
        recent = divs_moex[:5]
        div_lines = ["История дивидендов (MOEX):"]
        for d in recent:
            div_lines.append(
                f"  {d.get('registryclosedate', '?')}: {d.get('value', '?')} {d.get('currencyid', 'RUB')}"
            )
        sections.append("\n".join(div_lines))

    dohod = data.get("dohod") or {}
    if dohod:
        d_lines = []
        if dohod.get("dsi"):
            d_lines.append(f"DSI (стабильность дивидендов): {dohod['dsi']}")
        if dohod.get("next_amount"):
            d_lines.append(
                f"Прогноз дивиденда: {dohod['next_amount']} ₽"
                + (f" | доходность {dohod['next_yield']}" if dohod.get("next_yield") else "")
            )
            if dohod.get("next_date"):
                d_lines.append(f"Дата отсечки: {dohod['next_date']}")
        if dohod.get("history"):
            hist = dohod["history"][:3]
            d_lines.append("История (Dohod.ru): " + "; ".join(
                f"{h.get('period', '?')} — {h.get('amount', '?')} ({h.get('yield', '?')})"
                for h in hist
            ))
        if d_lines:
            sections.append("\n".join(d_lines))

    data_block = "\n\n".join(sections) if sections else "Подробные данные временно недоступны."

    prompt = (
        f"Ты — опытный российский инвестиционный аналитик. Проведи краткий анализ акции "
        f"{company_name} (тикер: {ticker}) на основе следующих данных:\n\n"
        f"{data_block}\n\n"
        f"Ответь строго в таком формате. Разрешены ТОЛЬКО теги <b> и <i> — никаких других HTML-тегов.\n\n"
        f"<b>📊 Оценка по мультипликаторам</b>\n"
        f"[2-3 предложения: дорого/дёшево относительно сектора, ключевые числа]\n\n"
        f"<b>💸 Дивидендный профиль</b>\n"
        f"[2-3 предложения: стабильность, доходность, прогноз]\n\n"
        f"<b>📈 Динамика бизнеса</b>\n"
        f"[2-3 предложения: рост выручки/прибыли, тренд]\n\n"
        f"<b>⚠️ Ключевые риски</b>\n"
        f"[2-3 конкретных риска для этой компании]\n\n"
        f"<b>✅ Инвестиционный тезис</b>\n"
        f"[1-2 предложения: покупать/держать/продавать и почему]\n\n"
        f"Используй только предоставленные данные. Не придумывай числа. "
        f"Если данных не хватает по какому-то разделу — честно скажи об этом. "
        f"НЕ используй теги ul, li, br, p, h1-h6, a или любые другие HTML-теги кроме b и i."
    )
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def analyze_financial_report_pdf(pdf_bytes: bytes, company_name: str, report_title: str) -> str:
    """Analyze a financial report PDF using Claude's document API."""
    import base64
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
    prompt = (
        f"Ты — опытный финансовый аналитик. Проанализируй финансовую отчётность компании "
        f"{company_name} ({report_title}).\n\n"
        f"Ответь структурированно:\n\n"
        f"<b>📊 Ключевые финансовые показатели</b>\n"
        f"[Выручка, EBITDA, чистая прибыль, долг — с динамикой год к году]\n\n"
        f"<b>💰 Рентабельность и эффективность</b>\n"
        f"[Маржинальность, ROE, ROA, оборачиваемость]\n\n"
        f"<b>🏦 Долговая нагрузка</b>\n"
        f"[Долг/EBITDA, покрытие процентов, структура обязательств]\n\n"
        f"<b>📈 Тренды и динамика</b>\n"
        f"[Рост/падение ключевых метрик, на что обратить внимание]\n\n"
        f"<b>⚠️ Риски из отчётности</b>\n"
        f"[Конкретные риски, упомянутые в документе]\n\n"
        f"<b>✅ Вывод</b>\n"
        f"[1-2 предложения: общая оценка финансового состояния компании]\n\n"
        f"Используй только данные из документа. Цифры приводи в рублях или валюте отчётности."
    )
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return response.content[0].text.strip()


async def explain_news_simple(analysis_text: str, product_id: str) -> str:
    from prompts.news_prompts import build_simple_explanation_prompt
    prompt = build_simple_explanation_prompt(analysis_text, product_id)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
