import asyncio
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    Message,
    URLInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from services import dohod, edisclosure, moex, smartlab
from services.claude import analyze_financial_report_pdf, analyze_stock
from services.subscription import is_product_subscribed
from states.stocks import StocksState


async def _check_stocks_access(callback: CallbackQuery) -> bool:
    if callback.from_user.id in ADMIN_IDS:
        return True
    if await is_product_subscribed(callback.from_user.id, "stocks"):
        return True
    from handlers.payment import show_stocks_paywall
    await show_stocks_paywall(callback)
    return False

router = Router()


# ─────────────── keyboards ───────────────

def _company_kb(ticker: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📈 Мультипликаторы", callback_data=f"stock:multi:{ticker}"),
        InlineKeyboardButton(text="💸 Дивиденды",       callback_data=f"stock:divs:{ticker}"),
    )
    kb.row(
        InlineKeyboardButton(text="📋 Стакан",          callback_data=f"stock:book:{ticker}"),
        InlineKeyboardButton(text="📄 Отчётность",      callback_data=f"stock:reports:{ticker}"),
    )
    kb.row(InlineKeyboardButton(text="🤖 AI Анализ", callback_data=f"stock:ai:{ticker}"))
    kb.row(InlineKeyboardButton(text="🔍 Другая компания", callback_data="stock:start"))
    kb.row(InlineKeyboardButton(text="◀️ Главное меню",   callback_data="back_to_menu"))
    return kb


def _back_kb(ticker: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ К компании", callback_data=f"stock:company:{ticker}"))
    return kb


# ─────────────── helpers ───────────────

def _fmt_price(price_data: dict | None) -> str:
    if not price_data or price_data.get("price") is None:
        return "цена недоступна"
    price = price_data["price"]
    change = price_data.get("change_pct")
    s = f"{price:,.2f} ₽".replace(",", " ")
    if change is not None:
        try:
            chf = float(change)
            arrow = "📈" if chf >= 0 else "📉"
            sign = "+" if chf >= 0 else ""
            s += f"  {arrow} {sign}{chf:.2f}%"
        except Exception:
            pass
    return s


def _fmt_vol(val) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
        if v >= 1e9:
            return f"{v/1e9:.1f} млрд ₽"
        if v >= 1e6:
            return f"{v/1e6:.1f} млн ₽"
        return f"{v:,.0f} ₽"
    except Exception:
        return "—"


# ─────────────── entry point ───────────────

@router.callback_query(F.data == "stock:start")
async def stock_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(StocksState.waiting_input)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
    await callback.message.edit_text(
        "🔍 <b>Анализ акций</b>\n\nВведите тикер или название компании:\n"
        "<i>Например: SBER, Газпром, Лукойл, YNDX</i>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(StocksState.waiting_input)
async def stock_search(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите тикер или название компании.")
        return

    await state.clear()
    status = await message.answer("🔍 Ищу на Московской бирже...")

    results = await moex.search_securities(query)

    if not results:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔍 Попробовать снова", callback_data="stock:start"))
        kb.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
        await status.edit_text(
            f"❌ Компания «{query}» не найдена на MOEX.\n\n"
            "Попробуйте точный тикер: <b>SBER</b>, <b>GAZP</b>, <b>LKOH</b>, <b>YNDX</b>",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        return

    if len(results) == 1:
        ticker = results[0]["secid"]
        name = results[0].get("shortname") or results[0].get("name") or ticker
        await state.update_data(company_name=name)
        await _show_company_card(status, ticker, name)
        return

    # Disambiguation
    kb = InlineKeyboardBuilder()
    for r in results[:6]:
        ticker = r["secid"]
        name = r.get("shortname") or r.get("name") or ticker
        kb.row(InlineKeyboardButton(
            text=f"{ticker}  —  {name}",
            callback_data=f"stock:company:{ticker}",
        ))
    kb.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu"))
    await status.edit_text(
        f"Найдено несколько компаний по «{query}». Выберите:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("stock:company:"))
async def stock_company(callback: CallbackQuery, state: FSMContext):
    ticker = callback.data[len("stock:company:"):]
    await callback.answer()
    fsm_data = await state.get_data()
    name = fsm_data.get("company_name") or ticker
    if name == ticker:
        results = await moex.search_securities(ticker)
        for r in results:
            if r.get("secid") == ticker:
                name = r.get("shortname") or r.get("name") or ticker
                break
    await _show_company_card(callback.message, ticker, name)


async def _show_company_card(target, ticker: str, name: str):
    price_data = await moex.get_security_price(ticker)
    lines = [
        f"📊 <b>{name}</b>  (<code>{ticker}</code>)\n",
        f"💰 <b>Цена:</b> {_fmt_price(price_data)}",
        f"📦 <b>Объём:</b> {_fmt_vol(price_data.get('vol_rub') if price_data else None)}",
    ]
    if price_data and price_data.get("open"):
        lines.append(
            f"📉 Open {price_data['open']} · High {price_data.get('high','—')} · Low {price_data.get('low','—')}"
        )
    lines.append("\nВыберите раздел:")
    text = "\n".join(lines)
    kb = _company_kb(ticker)
    if hasattr(target, "edit_text"):
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


# ─────────────── multipliers ───────────────

@router.callback_query(F.data.startswith("stock:multi:"))
async def stock_multipliers(callback: CallbackQuery):
    if not await _check_stocks_access(callback):
        return
    ticker = callback.data[len("stock:multi:"):]
    await callback.answer()
    await callback.message.edit_text(f"📈 Загружаю мультипликаторы {ticker}...")

    mult, fin = await asyncio.gather(
        smartlab.get_multipliers(ticker),
        smartlab.get_financials(ticker),
    )

    lines = [f"📈 <b>Мультипликаторы {ticker}</b>\n"]

    if mult:
        labels = {
            "p_e":          "P/E",
            "p_s":          "P/S",
            "ev_ebitda":    "EV/EBITDA",
            "p_bv":         "P/BV",
            "roe":          "ROE (%)",
            "roa":          "ROA (%)",
            "debt_ebitda":  "Долг/EBITDA",
            "div_yield":    "Дивиденды (%)",
            "market_cap_bln": "Капитализация (млрд ₽)",
        }
        for key, label in labels.items():
            if mult.get(key):
                lines.append(f"• <b>{label}:</b> {mult[key]}")
    else:
        lines.append("⚠️ Мультипликаторы временно недоступны")

    if fin and fin.get("years") and fin.get("metrics"):
        years = fin["years"]
        lines.append(f"\n📊 <b>Финансы, млрд ₽</b>  ({' / '.join(years)})")
        for key, label in [("revenue","Выручка"),("ebitda","EBITDA"),
                            ("net_profit","Чист. прибыль"),("net_debt","Чист. долг")]:
            vals = fin["metrics"].get(key)
            if vals:
                lines.append(f"• <b>{label}:</b> {' / '.join(str(v or '—') for v in vals)}")
    elif mult:
        lines.append("\n⚠️ Историческая финотчётность временно недоступна")

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=_back_kb(ticker).as_markup()
    )


# ─────────────── dividends ───────────────

@router.callback_query(F.data.startswith("stock:divs:"))
async def stock_dividends(callback: CallbackQuery):
    if not await _check_stocks_access(callback):
        return
    ticker = callback.data[len("stock:divs:"):]
    await callback.answer()
    await callback.message.edit_text(f"💸 Загружаю дивиденды {ticker}...")

    divs, dohod_info = await asyncio.gather(
        moex.get_dividends(ticker),
        dohod.get_dividend_info(ticker),
    )

    lines = [f"💸 <b>Дивиденды {ticker}</b>\n"]

    if dohod_info:
        if dohod_info.get("dsi"):
            try:
                dsi_val = float(dohod_info["dsi"])
                label = "🟢 высокая" if dsi_val >= 0.6 else ("🟡 средняя" if dsi_val >= 0.4 else "🔴 низкая")
                lines.append(f"📊 <b>DSI:</b> {dohod_info['dsi']} — стабильность {label}")
            except Exception:
                lines.append(f"📊 <b>DSI:</b> {dohod_info['dsi']}")
        if dohod_info.get("next_amount"):
            lines.append(f"\n🔮 <b>Прогноз:</b>")
            lines.append(f"• Дивиденд: <b>{dohod_info['next_amount']} ₽</b>")
            if dohod_info.get("next_yield"):
                lines.append(f"• Доходность: <b>{dohod_info['next_yield']}</b>")
            if dohod_info.get("next_date"):
                lines.append(f"• Дата отсечки: {dohod_info['next_date']}")
        if dohod_info.get("history"):
            lines.append(f"\n📜 <b>История:</b>")
            for h in dohod_info["history"][:5]:
                line = f"• {h.get('period','?')}: {h.get('amount','?')} ₽"
                if h.get("yield"):
                    line += f" | {h['yield']}"
                if h.get("date"):
                    line += f" | {h['date']}"
                lines.append(line)

    if divs:
        lines.append(f"\n📋 <b>История выплат (биржа):</b>")
        for d in divs[:8]:
            date = d.get("registryclosedate", "?")
            value = d.get("value", "?")
            curr = d.get("currencyid", "RUB")
            lines.append(f"• {date}: <b>{value} {curr}</b>")
    elif not dohod_info:
        lines.append("⚠️ Данные по дивидендам временно недоступны")

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=_back_kb(ticker).as_markup()
    )


# ─────────────── order book ───────────────

@router.callback_query(F.data.startswith("stock:book:"))
async def stock_orderbook(callback: CallbackQuery):
    if not await _check_stocks_access(callback):
        return
    ticker = callback.data[len("stock:book:"):]
    await callback.answer()
    await callback.message.edit_text(f"📋 Загружаю стакан {ticker}...")

    book = await moex.get_orderbook(ticker)

    if not book or (not book.get("buys") and not book.get("sells")):
        # Try to show at least current price
        price_data = await moex.get_security_price(ticker)
        msg = f"📋 <b>Стакан {ticker}</b>\n\n"
        if price_data and price_data.get("price"):
            msg += f"Последняя цена: <b>{_fmt_price(price_data)}</b>\n\n"
        msg += "⚠️ Стакан недоступен — биржа закрыта или нет активных заявок на данном уровне"
        await callback.message.edit_text(
            msg, parse_mode="HTML", reply_markup=_back_kb(ticker).as_markup()
        )
        return

    buys = book.get("buys", [])
    sells = book.get("sells", [])

    lines = [f"📋 <b>Стакан {ticker}</b>\n"]
    lines.append("<code>   Покупка              Продажа</code>")
    lines.append("<code>   Цена       Лоты     Цена       Лоты</code>")
    lines.append("<code>   ─────────────────────────────────────</code>")

    n = max(len(buys), len(sells), 1)
    for i in range(min(n, 8)):
        b_price = b_qty = s_price = s_qty = ""
        if i < len(buys):
            b = buys[i]
            b_price = str(b.get("PRICE", ""))
            b_qty = str(b.get("QUANTITY", ""))
        if i < len(sells):
            s = sells[i]
            s_price = str(s.get("PRICE", ""))
            s_qty = str(s.get("QUANTITY", ""))
        lines.append(f"<code>   {b_price:<10} {b_qty:<6}   {s_price:<10} {s_qty:<6}</code>")

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=_back_kb(ticker).as_markup()
    )


# ─────────────── financial reports ───────────────

@router.callback_query(F.data.startswith("stock:reports:"))
async def stock_reports(callback: CallbackQuery):
    if not await _check_stocks_access(callback):
        return
    ticker = callback.data[len("stock:reports:"):]
    await callback.answer()

    # Get company name from MOEX
    results = await moex.search_securities(ticker)
    company_name = ticker
    for r in results:
        if r.get("secid") == ticker:
            company_name = r.get("shortname") or r.get("name") or ticker
            break

    # e-disclosure.ru blocks server-side requests (403), so provide direct links
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📋 e-disclosure.ru (МСФО / РСБУ)",
        url=f"https://www.e-disclosure.ru/poisk-po-soobshheniyam?query={company_name}&eventType=55",
    ))
    kb.row(InlineKeyboardButton(
        text="📊 Smart-Lab — финансы по годам",
        url=f"https://smart-lab.ru/q/{ticker}/f/y/",
    ))
    kb.row(InlineKeyboardButton(
        text="🏛 MOEX — страница эмитента",
        url=f"https://www.moex.com/ru/issue.aspx?board=TQBR&code={ticker}",
    ))
    kb.row(InlineKeyboardButton(text="◀️ К компании", callback_data=f"stock:company:{ticker}"))

    text = (
        f"📄 <b>Отчётность {company_name} ({ticker})</b>\n\n"
        "Финансовые отчёты (МСФО, РСБУ) доступны на официальных платформах:\n\n"
        "• <b>e-disclosure.ru</b> — обязательное раскрытие по закону, годовые и полугодовые отчёты\n"
        "• <b>Smart-Lab</b> — выручка, EBITDA, прибыль по годам\n"
        "• <b>MOEX</b> — страница эмитента с последними новостями\n\n"
        "<i>Нажмите кнопку для перехода на источник</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


# Simple in-memory cache for reports (cleared on restart)
_report_cache: dict = {}


@router.callback_query(F.data.startswith("stock:pdf_dl:"))
async def stock_pdf_download(callback: CallbackQuery):
    parts = callback.data.split(":")
    # stock:pdf_dl:{ticker}:{idx}:{report_type}
    if len(parts) < 5:
        await callback.answer("Ошибка данных")
        return
    ticker = parts[2]
    idx = int(parts[3])
    report_type = parts[4]

    await callback.answer("Загружаю PDF...")

    reports_data = _report_cache.get(ticker)
    if not reports_data or not reports_data.get(report_type):
        await callback.message.answer("⚠️ Данные устарели. Откройте раздел отчётности снова.")
        return

    report_list = reports_data[report_type]
    if idx >= len(report_list):
        await callback.message.answer("⚠️ Отчёт не найден.")
        return

    rep = report_list[idx]
    url = rep["url"]
    title = rep.get("title", "Отчёт")[:50]

    status = await callback.message.answer(f"⏳ Скачиваю: {title}...")
    pdf_bytes = await edisclosure.download_pdf(url)

    if pdf_bytes is None:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🌐 Открыть в браузере", url=url))
        await status.edit_text(
            "⚠️ Не удалось скачать PDF (файл слишком большой или недоступен).\n"
            "Откройте напрямую:",
            reply_markup=kb.as_markup(),
        )
        return

    filename = f"{ticker}_{report_type}_{idx+1}.pdf"
    file = BufferedInputFile(pdf_bytes, filename=filename)
    await status.delete()
    await callback.message.answer_document(
        file,
        caption=f"📄 {title}\n<i>Источник: e-disclosure.ru</i>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("stock:pdf_ai:"))
async def stock_pdf_ai(callback: CallbackQuery):
    parts = callback.data.split(":")
    # stock:pdf_ai:{ticker}:{idx}:{report_type}
    if len(parts) < 5:
        await callback.answer("Ошибка данных")
        return
    ticker = parts[2]
    idx = int(parts[3])
    report_type = parts[4]

    await callback.answer("Анализирую отчётность...")

    reports_data = _report_cache.get(ticker)
    if not reports_data or not reports_data.get(report_type):
        await callback.message.answer("⚠️ Данные устарели. Откройте раздел отчётности снова.")
        return

    report_list = reports_data[report_type]
    if idx >= len(report_list):
        await callback.message.answer("⚠️ Отчёт не найден.")
        return

    rep = report_list[idx]
    url = rep["url"]
    title = rep.get("title", "Отчёт")[:60]

    status = await callback.message.answer(f"⏳ Скачиваю отчёт для анализа: {title}...")

    pdf_bytes = await edisclosure.download_pdf(url, max_bytes=20 * 1024 * 1024)

    if pdf_bytes is None:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🌐 Открыть в браузере", url=url))
        await status.edit_text(
            "⚠️ Файл слишком большой для AI анализа (лимит 20 МБ).\n"
            "Скачайте и изучите вручную:",
            reply_markup=kb.as_markup(),
        )
        return

    await status.edit_text("🤖 Анализирую отчётность через AI...")

    # Get company name
    results = await moex.search_securities(ticker)
    company_name = ticker
    for r in results:
        if r.get("secid") == ticker:
            company_name = r.get("shortname") or r.get("name") or ticker
            break

    try:
        analysis = await analyze_financial_report_pdf(pdf_bytes, company_name, title)
    except Exception as e:
        await status.edit_text(f"❌ Ошибка AI анализа: {e}")
        return

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ К отчётности", callback_data=f"stock:reports:{ticker}"))

    header = f"🤖 <b>AI Анализ отчётности: {company_name}</b>\n<i>{title}</i>\n\n"
    full_text = header + analysis

    # Telegram message limit is 4096 chars
    if len(full_text) > 4096:
        full_text = full_text[:4090] + "..."

    await status.edit_text(full_text, parse_mode="HTML", reply_markup=kb.as_markup())


# ─────────────── AI analysis (full) ───────────────

@router.callback_query(F.data.startswith("stock:ai:"))
async def stock_ai_analysis(callback: CallbackQuery):
    if not await _check_stocks_access(callback):
        return
    ticker = callback.data[len("stock:ai:"):]
    await callback.answer()
    await callback.message.edit_text("🤖 Собираю данные и анализирую...")

    price_data, divs, dohod_info, mult, fin = await asyncio.gather(
        moex.get_security_price(ticker),
        moex.get_dividends(ticker),
        dohod.get_dividend_info(ticker),
        smartlab.get_multipliers(ticker),
        smartlab.get_financials(ticker),
    )

    company_name = (price_data.get("shortname") if price_data else None) or ticker
    collected = {
        "price": price_data,
        "dividends_moex": divs,
        "dohod": dohod_info,
        "multipliers": mult,
        "financials": fin,
    }

    try:
        analysis = await analyze_stock(ticker, company_name, collected)
    except Exception as e:
        analysis = f"❌ Ошибка: {e}"

    header = f"🤖 <b>AI Анализ: {company_name} ({ticker})</b>\n\n"
    full = header + analysis
    if len(full) > 4096:
        full = full[:4090] + "..."

    try:
        await callback.message.edit_text(
            full, parse_mode="HTML", reply_markup=_back_kb(ticker).as_markup()
        )
    except Exception:
        # Claude may return unsupported HTML tags — strip all and send plain
        plain = re.sub(r"<[^>]+>", "", full)
        await callback.message.edit_text(
            plain, reply_markup=_back_kb(ticker).as_markup()
        )
