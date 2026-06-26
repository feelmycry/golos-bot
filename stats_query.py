import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from datetime import datetime

db = sqlite3.connect("training.db")
db.row_factory = sqlite3.Row

print("=== ПОЛЬЗОВАТЕЛИ ===")
users_count = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
print(f"Всего: {users_count}")
for u in db.execute("SELECT telegram_id, username, first_name, created_at FROM users").fetchall():
    print(f"  {u['first_name']} (@{u['username']}) — зарегистрирован: {u['created_at']}")

print()
print("=== СЕССИИ ===")
sess = db.execute("SELECT COUNT(*) total, SUM(is_complete) done FROM sessions").fetchone()
print(f"Всего: {sess['total']}, завершено: {sess['done']}")

print()
print("=== ДЕТАЛИ КАЖДОЙ СЕССИИ ===")
rows = db.execute("""
    SELECT u.first_name, s.stage, s.product, s.cohort,
           s.started_at, s.completed_at, s.is_complete,
           json_array_length(s.messages) as msg_count
    FROM sessions s JOIN users u ON s.user_id = u.telegram_id
    ORDER BY s.started_at DESC
""").fetchall()

for r in rows:
    if r["completed_at"]:
        try:
            t1 = datetime.fromisoformat(r["started_at"])
            t2 = datetime.fromisoformat(r["completed_at"])
            mins = round((t2 - t1).total_seconds() / 60, 1)
            dur = f"{mins} мин"
        except Exception:
            dur = "?"
    else:
        dur = "не завершена"
    print(f"  {r['first_name']} | этап={r['stage']} | продукт={r['product']} | когорта={r['cohort']} | {r['msg_count']} сообщ | {dur}")

print()
print("=== ПО ЭТАПАМ ===")
for r in db.execute("""
    SELECT stage, COUNT(*) cnt, SUM(is_complete) done,
           AVG(json_array_length(messages)) avg_msgs
    FROM sessions GROUP BY stage ORDER BY cnt DESC
""").fetchall():
    print(f"  {r['stage']}: {r['cnt']} сессий, завершено {int(r['done'] or 0)}, среднее {round(r['avg_msgs'], 1)} сообщ")

print()
print("=== ПО ПРОДУКТАМ ===")
for r in db.execute("""
    SELECT product, COUNT(*) cnt, SUM(is_complete) done
    FROM sessions WHERE product IS NOT NULL GROUP BY product ORDER BY cnt DESC
""").fetchall():
    print(f"  {r['product']}: {r['cnt']} сессий, завершено {int(r['done'] or 0)}")

db.close()
