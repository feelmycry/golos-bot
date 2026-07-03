import uvicorn
from fastapi import FastAPI
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


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
