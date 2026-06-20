from io import BytesIO
from openai import AsyncOpenAI
from config import GROQ_API_KEY

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


async def transcribe_voice(voice_bytes: bytes) -> str:
    bio = BytesIO(voice_bytes)
    bio.name = "voice.ogg"
    transcript = await _get_client().audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=bio,
        language="ru",
    )
    return transcript.text.strip()
