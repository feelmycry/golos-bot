# News Analysis Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить модуль анализа новостей в Telegram-бот Альфа-Банка с AI-анализом влияния на ОПИФ, ОМС, Стратегии и общий рынок РФ.

**Architecture:** Новый FSM-модуль (`states/news_analysis.py`, `handlers/news_analysis.py`) + сервис парсинга новостей (`services/news_fetcher.py`) + промпты с составом продуктов (`prompts/news_prompts.py`). Следует существующему паттерну проекта: один роутер на фичу, FSM для управления состоянием.

**Tech Stack:** aiogram 3.x, anthropic SDK, aiohttp, beautifulsoup4

## Global Constraints

- Python 3.10+, aiogram 3.x (InlineKeyboardBuilder, StatesGroup)
- Модель: `claude-sonnet-4-6`, max_tokens=400 для анализа
- Лимит новостей: 5 с каждого источника (10 итого)
- Лимит текста новости: 3000 символов
- Все тексты кнопок и сообщений на русском языке
- HTML parse_mode во всех сообщениях с форматированием

---

### Task 1: FSM States

**Files:**
- Create: `states/news_analysis.py`
- Modify: `states/__init__.py`

**Interfaces:**
- Produces: `NewsAnalysis` StatesGroup с состояниями `choosing_category`, `choosing_product`, `choosing_input_mode`, `waiting_news`

- [ ] **Step 1: Создать `states/news_analysis.py`**

```python
from aiogram.fsm.state import State, StatesGroup


class NewsAnalysis(StatesGroup):
    choosing_category = State()
    choosing_product = State()
    choosing_input_mode = State()
    waiting_news = State()
```

- [ ] **Step 2: Проверить `states/__init__.py`** и добавить импорт если файл не пустой

```python
from .news_analysis import NewsAnalysis
```

- [ ] **Step 3: Commit**

```bash
git add states/news_analysis.py states/__init__.py
git commit -m "feat: add NewsAnalysis FSM states"
```

---

### Task 2: News Prompts

**Files:**
- Create: `prompts/news_prompts.py`

**Interfaces:**
- Produces:
  - `PRODUCT_NAMES: dict[str, str]` — отображение product_id → русское название
  - `build_news_analysis_prompt(news_text: str, product_id: str) -> str`

- [ ] **Step 1: Создать `prompts/news_prompts.py`**

```python
PRODUCT_NAMES = {
    "general": "Общее влияние на рынок РФ",
    "obligplus": "ОПИФ Облигации Плюс",
    "obligincome": "ОПИФ Облигации с выплатой дохода",
    "balanced": "ОПИФ Сбалансированный с выплатой дохода",
    "stocks": "БПИФ Управляемые акции с выплатой дохода",
    "money": "БПИФ Денежный рынок",
    "bonds": "БПИФ Управляемые облигации",
    "gold": "ОМС Золото",
    "silver": "ОМС Серебро",
    "platinum": "ОМС Платина",
    "palladium": "ОМС Палладий",
    "tg": "Стратегия Тихая Гавань",
    "nav": "Стратегия Навигатор фондов",
    "eternal": "Стратегия Вечный портфель",
}

_PRODUCT_CONTEXTS = {
    "general": (
        "Анализируй влияние на общий российский фондовый рынок: индекс МосБиржи, "
        "рынок ОФЗ и корпоративных облигаций, курс рубля, инвестиционный климат. "
        "Ключевые факторы: ставка ЦБ РФ, геополитика, санкции, цены на нефть."
    ),
    "obligplus": (
        "ОПИФ «Облигации Плюс»: 50.3% ОФЗ (Минфин РФ), корпоративные облигации — "
        "ГТЛК 7.6%, РЖД 5.1%, Атомэнергопром 4.2%, РусГидро 3.8%, ВТБ 1.7%. "
        "Отрасли: госбумаги 50%, банки 11%, электроэнергетика 10%, промышленность 9%. "
        "Чувствителен к ставке ЦБ РФ (рост ставки = снижение цен облигаций) и кредитному качеству корпоратов."
    ),
    "obligincome": (
        "ОПИФ «Облигации с выплатой дохода»: ОФЗ 25.5% (Минфин 24.6%), "
        "банки и финансы 28.4% (ГТЛК 7.9%, Авто Финанс Банк 5.6%), "
        "промышленность 8.6%, электроэнергетика 6.8%. Ежеквартальные выплаты купонного дохода. "
        "Чувствителен к ставке ЦБ РФ и кредитному риску банков."
    ),
    "balanced": (
        "ОПИФ «Сбалансированный с выплатой дохода»: ~71% акции (Сбербанк 7.8%, "
        "HeadHunter 7.2%, Яндекс 6.0%, Т-Технологии 5.6%), ~16% ОФЗ, ~13% корп. облигации. "
        "Ежеквартальные выплаты. Чувствителен к рынку акций РФ, IT-сектору, ставке ЦБ РФ."
    ),
    "stocks": (
        "БПИФ «Управляемые акции с выплатой дохода»: ~100% акции РФ — нефтегаз 26% "
        "(Новатэк 7.9%, Лукойл 6.2%), финансы 21.5% (Сбербанк 9.6%), IT 16.5% "
        "(Ozon 8.3%, Яндекс 8.1%), потребительский 13.4%. Ежеквартальные дивиденды. "
        "Чувствителен к ценам на нефть, санкциям, геополитике, корп. событиям."
    ),
    "money": (
        "БПИФ «Денежный рынок»: 100% сделки обратного РЕПО с ЦК. "
        "Доходность напрямую привязана к ключевой ставке ЦБ РФ. "
        "Рост ставки ЦБ = рост доходности, снижение ставки = снижение доходности. "
        "Практически не реагирует на акции, нефть, геополитику."
    ),
    "bonds": (
        "БПИФ «Управляемые облигации»: 29% ОФЗ, корп. облигации 1-2 эшелона — "
        "банки 19.7%, энергетика 17%, промышленность 13.5%. "
        "Топ: ГТЛК 9.3%, Атомэнергопром 9.2%, Сэтл Групп 6.8%, РЖД 6.6%. "
        "Чувствителен к ставке ЦБ РФ и кредитному качеству корпоратов 1-2 эшелона."
    ),
    "gold": (
        "ОМС Золото: цена = мировые цены на золото × курс USD/RUB. "
        "Позитивные факторы: геополитика, инфляция, снижение ставки ФРС, ослабление доллара, покупки ЦБ. "
        "Негативные факторы: рост ставки ФРС, укрепление доллара, снижение напряжённости."
    ),
    "silver": (
        "ОМС Серебро: цена = мировые цены на серебро × курс USD/RUB. "
        "Двойная природа: инвестиционный + промышленный металл. "
        "Факторы: промышленный спрос (электроника, солнечная энергетика), геополитика, курс доллара. "
        "Более волатилен, чем золото."
    ),
    "platinum": (
        "ОМС Платина: цена = мировые цены на платину × курс USD/RUB. "
        "Преимущественно промышленный металл. "
        "Факторы: спрос автопрома (катализаторы дизельных двигателей), европейский промышленный спрос, "
        "баланс спроса и предложения на рынке."
    ),
    "palladium": (
        "ОМС Палладий: цена = мировые цены на палладий × курс USD/RUB. "
        "Применение: катализаторы бензиновых двигателей. "
        "Россия — крупнейший производитель (>40% мировой добычи). "
        "Факторы: спрос автопрома, санкции против РФ, переход на электромобили (долгосрочный негатив)."
    ),
    "tg": (
        "Стратегия «Тихая Гавань»: 40% Управляемые облигации + 40% Денежный рынок "
        "+ 10% флоатеры (переменный купон) + 10% ОФЗ. "
        "Консервативная, защитная. Максимально чувствительна к решениям ЦБ РФ. "
        "Слабо реагирует на акции и нефть."
    ),
    "nav": (
        "Стратегия «Навигатор фондов»: 50%+ Денежный рынок + 30% флоатеры "
        "+ 10% облигации с фикс. доходом + 3% акции + 2% золото. "
        "Ультраконсервативная. Наиболее чувствительна к ставке ЦБ РФ. "
        "Минимальная реакция на акции и геополитику."
    ),
    "eternal": (
        "Стратегия «Вечный портфель»: 30% Денежный рынок + 30% акции РФ "
        "+ 30% Управляемые облигации + 10% золото. "
        "Сбалансированная. Чувствительна к рынку акций РФ, ставке ЦБ, ценам на нефть, геополитике. "
        "Золото обеспечивает частичную защиту при кризисах."
    ),
}


def build_news_analysis_prompt(news_text: str, product_id: str) -> str:
    product_name = PRODUCT_NAMES.get(product_id, product_id)
    context = _PRODUCT_CONTEXTS.get(product_id, "")
    return (
        f"Ты — инвестиционный аналитик Альфа-Банка. Проанализируй влияние новости на продукт.\n\n"
        f"ПРОДУКТ: {product_name}\n"
        f"ХАРАКТЕРИСТИКИ: {context}\n\n"
        f"НОВОСТЬ:\n{news_text}\n\n"
        f"Ответь строго в формате:\n\n"
        f"📰 <b>Анализ влияния новости</b>\n\n"
        f"📌 <b>Продукт:</b> {product_name}\n"
        f"[📈 Влияние: Позитивное / 📉 Влияние: Негативное / ➡️ Влияние: Нейтральное]\n\n"
        f"[3–5 предложений: объясни механизм влияния конкретно для данного продукта, "
        f"ссылаясь на его состав]\n\n"
        f"⚠️ <i>Не является инвестиционной рекомендацией.</i>\n\n"
        f"Требования: строго 3–5 предложений, HTML-теги <b> и <i>, без повтора полного состава продукта."
    )
```

- [ ] **Step 2: Commit**

```bash
git add prompts/news_prompts.py
git commit -m "feat: add news analysis prompts with product contexts"
```

---

### Task 3: News Fetcher Service

**Files:**
- Create: `services/news_fetcher.py`

**Interfaces:**
- Produces:
  - `fetch_news(max_per_source: int = 5) -> list[dict]` — возвращает список `{"title": str, "text": str, "source": str}`
  - `format_news_for_prompt(news_items: list[dict]) -> str`

- [ ] **Step 1: Установить зависимость beautifulsoup4**

```bash
pip install beautifulsoup4
```

- [ ] **Step 2: Создать `services/news_fetcher.py`**

```python
import aiohttp
from bs4 import BeautifulSoup

_SOURCES = [
    {
        "url": "https://alfabank.ru/alfa-investor/",
        "name": "АльфаБанк Инвестор",
        "article_selectors": ["article", ".news-item", ".card", ".article-item"],
        "title_selectors": ["h2", "h3", ".title", ".card__title", "a"],
        "text_selectors": ["p", ".description", ".card__text", ".summary"],
    },
    {
        "url": "https://bcs-express.ru/novosti-i-analitika",
        "name": "БКС Экспресс",
        "article_selectors": ["article", ".article-list__item", ".news-list__item", ".post"],
        "title_selectors": ["h2", "h3", ".article-list__title", ".title", "a"],
        "text_selectors": ["p", ".article-list__text", ".lead", ".description"],
    },
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AlphaBot/1.0)"}


async def fetch_news(max_per_source: int = 5) -> list[dict]:
    results = []
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
        for source in _SOURCES:
            try:
                items = await _fetch_source(session, source, max_per_source)
                results.extend(items)
            except Exception:
                continue
    return results[:10]


async def _fetch_source(session: aiohttp.ClientSession, source: dict, limit: int) -> list[dict]:
    async with session.get(source["url"]) as resp:
        if resp.status != 200:
            return []
        html = await resp.text(errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    articles = []

    for selector in source["article_selectors"]:
        found = soup.select(selector)
        if len(found) >= 2:
            for item in found[:limit]:
                title = _extract_text(item, source["title_selectors"])
                text = _extract_text(item, source["text_selectors"])
                if title and len(title) > 10:
                    articles.append({
                        "title": title[:200],
                        "text": text[:400] if text else "",
                        "source": source["name"],
                    })
            break

    # Fallback: grab all links that look like article titles
    if not articles:
        for a in soup.find_all("a", href=True)[:limit * 3]:
            text = a.get_text(strip=True)
            if len(text) > 20 and len(text) < 200:
                articles.append({"title": text, "text": "", "source": source["name"]})
                if len(articles) >= limit:
                    break

    return articles[:limit]


def _extract_text(element, selectors: list[str]) -> str:
    for selector in selectors:
        found = element.select_one(selector)
        if found:
            text = found.get_text(strip=True)
            if text:
                return text
    return ""


def format_news_for_prompt(news_items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item["text"]:
            lines.append(f"   {item['text']}")
    return "\n".join(lines)
```

- [ ] **Step 3: Commit**

```bash
git add services/news_fetcher.py
git commit -m "feat: add news fetcher service for alfa-investor and bcs-express"
```

---

### Task 4: Claude analyze_news_impact function

**Files:**
- Modify: `services/claude.py`

**Interfaces:**
- Consumes: `build_news_analysis_prompt(news_text, product_id)` из `prompts.news_prompts`
- Produces: `analyze_news_impact(news_text: str, product_id: str) -> str`

- [ ] **Step 1: Добавить функцию в конец `services/claude.py`**

```python
async def analyze_news_impact(news_text: str, product_id: str) -> str:
    from prompts.news_prompts import build_news_analysis_prompt
    prompt = build_news_analysis_prompt(news_text, product_id)
    response = await _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
```

- [ ] **Step 2: Commit**

```bash
git add services/claude.py
git commit -m "feat: add analyze_news_impact to claude service"
```

---

### Task 5: News Analysis Handler

**Files:**
- Create: `handlers/news_analysis.py`

**Interfaces:**
- Consumes:
  - `NewsAnalysis` из `states.news_analysis`
  - `PRODUCT_NAMES` из `prompts.news_prompts`
  - `analyze_news_impact(news_text, product_id)` из `services.claude`
  - `fetch_news()`, `format_news_for_prompt()` из `services.news_fetcher`
- Produces: `router` (aiogram Router) для регистрации в `bot.py`

- [ ] **Step 1: Создать `handlers/news_analysis.py`**

```python
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states.news_analysis import NewsAnalysis
from prompts.news_prompts import PRODUCT_NAMES
from services.claude import analyze_news_impact
from services.news_fetcher import fetch_news, format_news_for_prompt

router = Router()

_OPIF_PRODUCTS = {"obligplus", "obligincome", "balanced", "stocks", "money", "bonds"}
_OMS_PRODUCTS = {"gold", "silver", "platinum", "palladium"}
_STRATEGY_PRODUCTS = {"tg", "nav", "eternal"}


# ── Keyboards ────────────────────────────────────────────────────────────────

def _news_main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🌍 Общее влияние на рынок", callback_data="news:cat:general")
    b.button(text="📊 На ОПИФ", callback_data="news:cat:opif")
    b.button(text="🥇 На ОМС", callback_data="news:cat:oms")
    b.button(text="⚡ На Стратегии", callback_data="news:cat:strategy")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


def _opif_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Облигации Плюс", callback_data="news:prod:obligplus")
    b.button(text="Облигации с выплатой дохода", callback_data="news:prod:obligincome")
    b.button(text="Сбалансированный с выплатой дохода", callback_data="news:prod:balanced")
    b.button(text="Управляемые акции с выплатой дохода", callback_data="news:prod:stocks")
    b.button(text="Денежный рынок", callback_data="news:prod:money")
    b.button(text="Управляемые облигации", callback_data="news:prod:bonds")
    b.button(text="◀️ Назад", callback_data="news:menu")
    b.adjust(1)
    return b.as_markup()


def _oms_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🥇 Золото", callback_data="news:prod:gold")
    b.button(text="🥈 Серебро", callback_data="news:prod:silver")
    b.button(text="⬜ Платина", callback_data="news:prod:platinum")
    b.button(text="⬜ Палладий", callback_data="news:prod:palladium")
    b.button(text="◀️ Назад", callback_data="news:menu")
    b.adjust(1)
    return b.as_markup()


def _strategy_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🏝 Тихая Гавань", callback_data="news:prod:tg")
    b.button(text="🧭 Навигатор фондов", callback_data="news:prod:nav")
    b.button(text="♾ Вечный портфель", callback_data="news:prod:eternal")
    b.button(text="◀️ Назад", callback_data="news:menu")
    b.adjust(1)
    return b.as_markup()


def _input_mode_kb(product_id: str):
    b = InlineKeyboardBuilder()
    b.button(text="📝 Вставить новость", callback_data=f"news:input:manual:{product_id}")
    b.button(text="🔄 Новости за 48 часов", callback_data=f"news:input:auto:{product_id}")
    b.button(text="◀️ Назад", callback_data=f"news:back:{product_id}")
    b.adjust(1)
    return b.as_markup()


def _after_analysis_kb(product_id: str):
    b = InlineKeyboardBuilder()
    b.button(text="📝 Ещё новость", callback_data=f"news:input:manual:{product_id}")
    b.button(text="◀️ К продуктам", callback_data=f"news:back:{product_id}")
    b.button(text="🏠 Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


# ── Category handlers ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "news:menu")
async def news_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(NewsAnalysis.choosing_category)
    await callback.message.edit_text(
        "📰 <b>Анализ новостей</b>\n\nВыберите категорию:",
        parse_mode="HTML",
        reply_markup=_news_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:general")
async def news_cat_general(callback: CallbackQuery, state: FSMContext):
    await state.update_data(product_id="general")
    await state.set_state(NewsAnalysis.choosing_input_mode)
    await callback.message.edit_text(
        f"🌍 <b>{PRODUCT_NAMES['general']}</b>\n\nВыберите способ анализа:",
        parse_mode="HTML",
        reply_markup=_input_mode_kb("general"),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:opif")
async def news_cat_opif(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewsAnalysis.choosing_product)
    await callback.message.edit_text(
        "📊 <b>ОПИФ — выберите фонд:</b>",
        parse_mode="HTML",
        reply_markup=_opif_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:oms")
async def news_cat_oms(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewsAnalysis.choosing_product)
    await callback.message.edit_text(
        "🥇 <b>ОМС — выберите металл:</b>",
        parse_mode="HTML",
        reply_markup=_oms_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:strategy")
async def news_cat_strategy(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewsAnalysis.choosing_product)
    await callback.message.edit_text(
        "⚡ <b>Стратегии — выберите стратегию:</b>",
        parse_mode="HTML",
        reply_markup=_strategy_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("news:prod:"))
async def news_select_product(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:prod:"):]
    await state.update_data(product_id=product_id)
    await state.set_state(NewsAnalysis.choosing_input_mode)
    product_name = PRODUCT_NAMES.get(product_id, product_id)
    await callback.message.edit_text(
        f"📌 <b>{product_name}</b>\n\nВыберите способ анализа:",
        parse_mode="HTML",
        reply_markup=_input_mode_kb(product_id),
    )
    await callback.answer()


# ── Input mode handlers ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("news:input:manual:"))
async def news_input_manual(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:input:manual:"):]
    await state.update_data(product_id=product_id)
    await state.set_state(NewsAnalysis.waiting_news)
    product_name = PRODUCT_NAMES.get(product_id, product_id)
    await callback.message.edit_text(
        f"📝 <b>Введите текст новости</b>\n\n"
        f"Продукт: <i>{product_name}</i>\n\n"
        f"Вставьте или напишите текст новости для анализа:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("news:input:auto:"))
async def news_input_auto(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:input:auto:"):]
    product_name = PRODUCT_NAMES.get(product_id, product_id)

    await callback.answer()
    status = await callback.message.edit_text("⏳ Ищу свежие новости...")

    news_items = await fetch_news()

    if not news_items:
        await status.edit_text(
            "❌ Свежих новостей не найдено. Попробуйте вставить новость вручную.",
            reply_markup=_input_mode_kb(product_id),
        )
        return

    news_text = format_news_for_prompt(news_items)
    await status.edit_text(
        f"🤔 Анализирую {len(news_items)} новостей для <b>{product_name}</b>...",
        parse_mode="HTML",
    )

    try:
        result = await analyze_news_impact(news_text, product_id)
        await status.edit_text(result, parse_mode="HTML", reply_markup=_after_analysis_kb(product_id))
    except Exception as e:
        await status.edit_text(f"❌ Ошибка анализа: {e}", reply_markup=_input_mode_kb(product_id))


# ── Text input handler ────────────────────────────────────────────────────────

@router.message(NewsAnalysis.waiting_news, F.text)
async def news_receive_text(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id", "general")
    product_name = PRODUCT_NAMES.get(product_id, product_id)

    news_text = message.text[:3000]
    warning = ""
    if len(message.text) > 3000:
        warning = "⚠️ Текст обрезан до 3000 символов.\n\n"

    status = await message.answer(
        f"🤔 Анализирую новость для <b>{product_name}</b>...",
        parse_mode="HTML",
    )

    try:
        result = await analyze_news_impact(news_text, product_id)
        await status.edit_text(
            warning + result,
            parse_mode="HTML",
            reply_markup=_after_analysis_kb(product_id),
        )
    except Exception as e:
        await status.edit_text(f"❌ Ошибка анализа: {e}")


@router.message(NewsAnalysis.waiting_news, ~F.text)
async def news_wrong_input(message: Message):
    await message.answer(
        "📝 Пожалуйста, отправьте <b>текст</b> новости.",
        parse_mode="HTML",
    )


# ── Back navigation ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("news:back:"))
async def news_back(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:back:"):]
    if product_id == "general":
        await news_menu(callback, state)
    elif product_id in _OPIF_PRODUCTS:
        await news_cat_opif(callback, state)
    elif product_id in _OMS_PRODUCTS:
        await news_cat_oms(callback, state)
    elif product_id in _STRATEGY_PRODUCTS:
        await news_cat_strategy(callback, state)
    else:
        await news_menu(callback, state)
```

- [ ] **Step 2: Commit**

```bash
git add handlers/news_analysis.py
git commit -m "feat: add news analysis handler with full navigation tree"
```

---

### Task 6: Update start handler + register router

**Files:**
- Modify: `handlers/start.py`
- Modify: `bot.py`

**Interfaces:**
- Consumes: `news_analysis.router` из `handlers.news_analysis`

- [ ] **Step 1: Обновить `handlers/start.py`** — изменить `_main_kb()` и текст `/start`

В функции `_main_kb()` заменить:
```python
def _main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Начать тренировку", callback_data="start_training")
    b.button(text="📊 Моя статистика", callback_data="show_stats")
    b.adjust(1)
    return b.as_markup()
```
на:
```python
def _main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Начать тренировку", callback_data="start_training")
    b.button(text="📰 Анализ новостей", callback_data="news:menu")
    b.button(text="📊 Моя статистика", callback_data="show_stats")
    b.adjust(1)
    return b.as_markup()
```

В функции `cmd_start()` заменить текст сообщения:
```python
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        f"Я — тренажёр по продажам инвестиционных продуктов <b>Альфа-Банка</b> "
        f"и помощник по анализу новостей на инвестиционные продукты.\n\n"
        f"Помогу отработать навыки продаж:\n"
        f"• НСЖ — Альфа-Страхование жизни\n"
        f"• ПДС — Альфа НПФ\n"
        f"• ОПИФ — Альфа-Капитал\n"
        f"• ОМС — металлические счета\n"
        f"• Стратегии автоследования — Альфа-Инвестиции\n\n"
        f"Отвечай <b>голосовыми сообщениями</b> — я распознаю и анализирую твой ответ через AI.",
        parse_mode="HTML",
        reply_markup=_main_kb(),
    )
```

- [ ] **Step 2: Обновить `bot.py`** — добавить импорт и роутер

Добавить импорт:
```python
from handlers import start, setup, dialog, news_analysis
```

Добавить роутер после `dp.include_router(dialog.router)`:
```python
    dp.include_router(news_analysis.router)
```

- [ ] **Step 3: Commit**

```bash
git add handlers/start.py bot.py
git commit -m "feat: add news analysis button to main menu and register router"
```
