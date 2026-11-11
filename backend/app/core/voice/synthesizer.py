"""
Text-to-speech via ElevenLabs.

Also missing entirely from the original draft. Uses a direct HTTP call
(httpx) instead of the `elevenlabs` SDK to avoid pinning to a specific SDK
version — the REST API is stable and this keeps the dependency footprint
small (you already have httpx for the Trello client).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from app.config import settings

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


@dataclass
class SpeechResult:
    audio_bytes: bytes
    content_type: str = "audio/mpeg"


class Synthesizer:
    def __init__(self) -> None:
        self.api_key = settings.elevenlabs_api_key
        self.voice_id = settings.elevenlabs_voice_id

    async def synthesize(self, text: str, language: str = "fr") -> SpeechResult:
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured")

        url = ELEVENLABS_TTS_URL.format(voice_id=self.voice_id)
        headers = {
            "xi-api-key": self.api_key,
            "content-type": "application/json",
            "accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",  # handles fr + en in one model
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return SpeechResult(audio_bytes=resp.content)

    def to_base64(self, speech: SpeechResult) -> str:
        return base64.b64encode(speech.audio_bytes).decode("utf-8")


synthesizer = Synthesizer()