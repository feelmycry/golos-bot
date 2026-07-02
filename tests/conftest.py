import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["DEV_USER_ID"] = "99999"  # bypass auth in tests

from api.server import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
