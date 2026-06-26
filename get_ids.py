import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
db = sqlite3.connect("training.db")
db.row_factory = sqlite3.Row
for u in db.execute("SELECT telegram_id, username, first_name FROM users").fetchall():
    print(u["first_name"], u["username"], u["telegram_id"])
db.close()
