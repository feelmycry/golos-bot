"""
Extract course data from investment-course/js/course-data.js
and produce data/course.json for the Telegram bot.

Run once:  python scripts/extract_course.py
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

JS_PATH = Path(__file__).parent.parent.parent / "OMS" / "investment-course" / "js" / "course-data.js"
OUT_PATH = Path(__file__).parent.parent / "data" / "course.json"


# ─── HTML → plain text converter ─────────────────────────────────────────────

class _HtmlToText(HTMLParser):
    BLOCK_TAGS = {"h2", "h3", "h4", "p", "li", "div", "br"}
    BOLD_TAGS  = {"h2", "h3", "h4", "strong", "b"}
    CODE_TAGS  = {"code", "pre"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._in_bold = 0
        self._in_code = 0
        self._in_li   = False
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag in self.BOLD_TAGS:
            self._in_bold += 1
            if tag in ("h2", "h3", "h4"):
                self._parts.append("\n\n")

        if tag in self.CODE_TAGS:
            self._in_code += 1
            self._parts.append("`")

        if tag == "li":
            self._in_li = True
            self._parts.append("\n• ")

        if tag == "br":
            self._parts.append("\n")

        if tag == "div":
            self._parts.append("\n")
            if "callout" in cls:
                self._parts.append("💡 ")
            elif "formula" in cls:
                self._in_code += 1
                self._parts.append("`")
            elif "example" in cls:
                self._parts.append("📌 ")

    def handle_endtag(self, tag):
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        if tag in self.BOLD_TAGS:
            self._in_bold = max(0, self._in_bold - 1)
            self._parts.append("\n")

        if tag in self.CODE_TAGS:
            self._in_code = max(0, self._in_code - 1)
            self._parts.append("`")

        if tag in ("div",):
            parent_cls = ""
            if self._tag_stack:
                self._parts.append("\n")
            if self._in_code > 0:  # formula div ended
                pass

        if tag == "li":
            self._in_li = False

        if tag in ("p", "ul", "ol"):
            self._parts.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self._in_bold:
            text = f"<b>{text}</b>"
        if self._in_code:
            pass  # already wrapped in backticks
        self._parts.append(text)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse 3+ newlines into 2
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_tg(html: str) -> str:
    parser = _HtmlToText()
    parser.feed(html)
    return parser.get_text()


# ─── JS parser ───────────────────────────────────────────────────────────────

def extract_js(js_text: str) -> dict:
    """
    Extract modules, chapters, lessons, and quizzes from the JS file.
    Strategy: locate each lesson block by its id pattern, then extract fields.
    """
    result = {"modules": []}

    # ── Module-level metadata ─────────────────────────────────────────────────
    # Match top-level module objects: {id:'m1', title:..., level:..., ...}
    mod_pattern = re.compile(
        r"\{\s*id\s*[=:]\s*['\"](?P<id>m\d+)['\"]"
        r".*?title\s*[=:]\s*['\"](?P<title>[^'\"]+)['\"]"
        r".*?level\s*[=:]\s*['\"](?P<level>[^'\"]+)['\"]"
        r".*?icon\s*[=:]\s*['\"](?P<icon>[^'\"]*)['\"]"
        r".*?description\s*[=:]\s*['\"](?P<desc>[^'\"]+)['\"]",
        re.DOTALL,
    )
    mod_meta: dict[str, dict] = {}
    for m in mod_pattern.finditer(js_text):
        mod_meta[m.group("id")] = {
            "id": m.group("id"),
            "title": m.group("title"),
            "level": m.group("level"),
            "icon": m.group("icon"),
            "description": m.group("desc"),
            "lessons": [],
        }

    # ── Lessons ──────────────────────────────────────────────────────────────
    # Find each lesson block by id
    lesson_id_positions = list(re.finditer(
        r"id\s*[=:]\s*['\"](?P<lid>m(?P<mid>\d+)l(?P<lnum>\d+))['\"]",
        js_text,
    ))

    for i, match in enumerate(lesson_id_positions):
        lid   = match.group("lid")
        mid   = f"m{match.group('mid')}"
        start = match.start()
        # Approximate end: next lesson id or 6000 chars, whichever comes first
        end   = lesson_id_positions[i + 1].start() if i + 1 < len(lesson_id_positions) else start + 8000
        block = js_text[start: min(end + 2000, start + 8000)]

        title_m = re.search(r"title\s*[=:]\s*['\"]([^'\"]+)['\"]", block)
        dur_m   = re.search(r"duration\s*[=:]\s*(\d+)", block)
        xp_m    = re.search(r"xp\s*[=:]\s*(\d+)", block)
        paid_m  = re.search(r"isPaid\s*[=:]\s*(true|false)", block)
        ch_m    = re.search(r"chapterIdx\s*[=:]\s*(\d+)", block)

        title  = title_m.group(1) if title_m else lid
        dur    = int(dur_m.group(1)) if dur_m else 0
        xp     = int(xp_m.group(1)) if xp_m else 0
        is_paid = paid_m.group(1) == "true" if paid_m else False
        ch_idx = int(ch_m.group(1)) if ch_m else 0

        # ── Content (backtick template literal) ──────────────────────────────
        content_raw = ""
        # content may come before or after quiz in the block
        # search for  content: `...`  pattern (backtick literal)
        full_block = js_text[start: start + 8000]
        content_match = re.search(r"content\s*[=:]\s*`([\s\S]*?)`\s*[,\}]", full_block)
        if content_match:
            content_raw = content_match.group(1).strip()
        content_text = html_to_tg(content_raw) if content_raw else ""

        # ── Quiz ──────────────────────────────────────────────────────────────
        quiz = []
        # Quiz objects look like: {q:'...', options:[...], correct:N, explanation:'...'}
        quiz_items = re.findall(
            r"\{\s*q\s*[=:]\s*['\"]([^'\"]+)['\"]"
            r"[\s\S]*?options\s*[=:]\s*\[([^\]]+)\]"
            r"[\s\S]*?correct\s*[=:]\s*(\d+)"
            r"(?:[\s\S]*?explanation\s*[=:]\s*['\"]([^'\"]*)['\"])?",
            full_block,
        )
        for q_text, opts_raw, correct_str, expl in quiz_items:
            options = [o.strip().strip("'\"") for o in opts_raw.split(",") if o.strip().strip("'\"")]
            quiz.append({
                "q": q_text,
                "options": options,
                "correct": int(correct_str),
                "explanation": expl or "",
            })

        lesson = {
            "id": lid,
            "title": title,
            "duration": dur,
            "xp": xp,
            "is_paid": is_paid,
            "chapter_idx": ch_idx,
            "content": content_text,
            "quiz": quiz,
        }

        if mid in mod_meta:
            mod_meta[mid]["lessons"].append(lesson)

    # ── Chapter titles ────────────────────────────────────────────────────────
    # Find chapter title arrays per module section
    chapter_blocks = re.findall(
        r"chapters\s*[=:]\s*\[([\s\S]*?)(?=\n\s*\][\s,\n]*(?:price|freeCount|\}|//|$))",
        js_text,
    )
    ch_title_pattern = re.compile(r"\{\s*title\s*[=:]\s*['\"]([^'\"]+)['\"]")
    for mod_key, mod_data in mod_meta.items():
        # Assign chapter names by scanning near module
        pass  # chapter names not critical for bot nav, lessons self-describe chapters

    result["modules"] = list(mod_meta.values())
    return result


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if not JS_PATH.exists():
        print(f"ERROR: JS file not found at {JS_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {JS_PATH} ...")
    js_text = JS_PATH.read_text(encoding="utf-8")

    print("Extracting course data ...")
    course = extract_js(js_text)

    pass  # stats printed after save

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(course, ensure_ascii=False, indent=2), encoding="utf-8")

    total_lessons = sum(len(m["lessons"]) for m in course["modules"])
    for mod in course["modules"]:
        n = len(mod["lessons"])
        with_content = sum(1 for l in mod["lessons"] if l["content"])
        with_quiz = sum(1 for l in mod["lessons"] if l["quiz"])
        print(f"  {mod['id']}: {mod['title']} — {n} lessons, {with_content} w/content, {with_quiz} w/quiz")
    print(f"Total: {len(course['modules'])} modules, {total_lessons} lessons")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
