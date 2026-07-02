import os
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import TELEGRAM_TOKEN
from api.auth import validate_init_data

DEV_USER_ID = int(os.getenv("DEV_USER_ID", "0"))

app = FastAPI(title="Golos Game API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_current_user(request: Request) -> int:
    if DEV_USER_ID:
        return DEV_USER_ID
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data")
    try:
        user_data = validate_init_data(init_data, TELEGRAM_TOKEN)
        return int(user_data["id"])
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid init data")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
