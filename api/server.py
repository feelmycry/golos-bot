import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routers import profile as profile_router
from api.routers import map as map_router
from api.routers import exchange as exchange_router
from api.routers import leaderboard as lb_router, daily as daily_router

app = FastAPI(title="Golos Game API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile_router.router)
app.include_router(map_router.router)
app.include_router(exchange_router.router)
app.include_router(lb_router.router)
app.include_router(daily_router.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/debug")
async def debug(request: Request):
    token = request.query_params.get("t", "")
    uid = None
    if token:
        from services.miniapp_auth import validate_token
        uid = validate_token(token)
    return {
        "token_present": bool(token),
        "token_valid": uid is not None,
        "resolved_user": uid,
        "init_data_present": bool(request.headers.get("X-Telegram-Init-Data")),
        "user_id_header": request.headers.get("X-Telegram-User-Id", ""),
    }


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port)
