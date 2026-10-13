from __future__ import annotations
import os, uuid, base64, asyncio
from pathlib import Path
import httpx
from audio_utils import OUTPUTS

OPENAI_BASE = "https://api.openai.com/v1"
ELEVEN_BASE = "https://api.elevenlabs.io/v1"
RESPEECHER_BASE = "https://api.respeecher.com"
SPEECHIFY_BASE = "https://api.speechify.ai"
KITS_BASE = "https://arpeggi.io/api/kits/v1"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


async def openai_tts(text: str, voice: str, speed: float, instructions: str | None = None) -> Path:
    key = _require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    payload = {"model": model, "voice": voice, "input": text, "response_format": "mp3", "speed": speed}
    if instructions:
        payload["instructions"] = instructions
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OPENAI_BASE}/audio/speech", headers={"Authorization": f"Bearer {key}"}, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"OpenAI TTS failed: {r.status_code} {r.text[:400]}")
    out = OUTPUTS / f"tts_{uuid.uuid4().hex}.mp3"
    out.write_bytes(r.content)
    return out


async def eleven_tts(text: str, voice_id: str) -> Path:
    key = _require_env("ELEVENLABS_API_KEY")
    payload = {"text": text, "model_id": "eleven_multilingual_v2"}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ELEVEN_BASE}/text-to-speech/{voice_id}?output_format=mp3_44100_128",
            headers={"xi-api-key": key, "Content-Type": "application/json"}, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs TTS failed: {r.status_code} {r.text[:400]}")
    out = OUTPUTS / f"tts_{uuid.uuid4().hex}.mp3"
    out.write_bytes(r.content)
    return out


async def eleven_voice_convert(audio_path: Path, voice_id: str) -> Path:
    key = _require_env("ELEVENLABS_API_KEY")
    async with httpx.AsyncClient(timeout=300) as client:
        with audio_path.open("rb") as f:
            files = {"audio": (audio_path.name, f, "audio/wav")}
            data = {"model_id": "eleven_multilingual_sts_v2"}
            r = await client.post(
                f"{ELEVEN_BASE}/speech-to-speech/{voice_id}?output_format=mp3_44100_128",
                headers={"xi-api-key": key}, files=files, data=data)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs voice conversion failed: {r.status_code} {r.text[:400]}")
    out = OUTPUTS / f"converted_{uuid.uuid4().hex}.mp3"
    out.write_bytes(r.content)
    return out


async def eleven_sfx(prompt: str, duration_seconds: float | None = None) -> Path:
    key = _require_env("ELEVENLABS_API_KEY")
    payload = {"text": prompt}
    if duration_seconds is not None:
        payload["duration_seconds"] = max(0.5, min(22, duration_seconds))
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(f"{ELEVEN_BASE}/sound-generation", headers={"xi-api-key": key, "Content-Type": "application/json"}, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"Sound generation failed: {r.status_code} {r.text[:400]}")
    out = OUTPUTS / f"sfx_{uuid.uuid4().hex}.mp3"
    out.write_bytes(r.content)
    return out


async def eleven_shared_voices(search: str = "", category: str = "professional", page_size: int = 50) -> dict:
    """Return shared Professional Voice Clones from ElevenLabs Voice Library."""
    key = _require_env("ELEVENLABS_API_KEY")
    params = {"page_size": min(max(page_size, 1), 100), "sort": "trending"}
    if search:
        params["search"] = search
    if category:
        params["category"] = category
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{ELEVEN_BASE}/shared-voices", headers={"xi-api-key": key}, params=params)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs Voice Library lookup failed: {r.status_code} {r.text[:400]}")
    return r.json()


async def eleven_add_shared_voice(public_owner_id: str, voice_id: str, new_name: str) -> str:
    key = _require_env("ELEVENLABS_API_KEY")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ELEVEN_BASE}/voices/add/{public_owner_id}/{voice_id}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"new_name": new_name, "bookmarked": True},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Could not add ElevenLabs shared voice: {r.status_code} {r.text[:400]}")
    return r.json()["voice_id"]


async def respeecher_list_voices() -> list[dict]:
    key = _require_env("RESPEECHER_API_KEY")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{RESPEECHER_BASE}/v1/public/tts/en-rt/voices",
            headers={"X-API-Key": key},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Respeecher voice lookup failed: {r.status_code} {r.text[:400]}")
    return r.json()


async def respeecher_tts(text: str, voice_id: str) -> Path:
    key = _require_env("RESPEECHER_API_KEY")
    payload = {"transcript": text, "voice": {"id": voice_id}}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{RESPEECHER_BASE}/v1/public/tts/en-rt/tts/bytes",
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Respeecher TTS failed: {r.status_code} {r.text[:400]}")
    out = OUTPUTS / f"respeecher_{uuid.uuid4().hex}.wav"
    out.write_bytes(r.content)
    return out


async def speechify_list_voices(limit: int = 100, locale: str = "en") -> dict:
    key = _require_env("SPEECHIFY_API_KEY")
    params = {"limit": min(max(limit, 1), 200), "type": "shared"}
    if locale:
        params["locale"] = locale
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{SPEECHIFY_BASE}/v1/voices", headers={"Authorization": f"Bearer {key}"}, params=params)
        if r.status_code >= 400:
            raise RuntimeError(f"Speechify voice lookup failed: {r.status_code} {r.text[:400]}")
    return r.json()


async def speechify_tts(text: str, voice_id: str) -> Path:
    key = _require_env("SPEECHIFY_API_KEY")
    payload = {"input": text, "voice_id": voice_id, "audio_format": "mp3", "model": "simba-3.2"}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{SPEECHIFY_BASE}/v1/audio/speech", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"Speechify TTS failed: {r.status_code} {r.text[:400]}")
    data = r.json()
    out = OUTPUTS / f"speechify_{uuid.uuid4().hex}.mp3"
    out.write_bytes(base64.b64decode(data["audio_data"]))
    return out


async def kits_list_voice_models(page: int = 1, per_page: int = 50, my_models: bool = False) -> dict:
    key = _require_env("KITS_API_KEY")
    params = {"page": max(1, page), "perPage": min(max(per_page, 1), 100), "order": "asc"}
    if my_models:
        params["myModels"] = "true"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{KITS_BASE}/voice-models",
            headers={"Authorization": f"Bearer {key}"},
            params=params,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Kits voice-model lookup failed: {r.status_code} {r.text[:400]}")
    return r.json()


async def kits_voice_convert(audio_path: Path, voice_model_id: str, timeout_seconds: int = 300) -> Path:
    key = _require_env("KITS_API_KEY")
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=120) as client:
        with audio_path.open("rb") as f:
            r = await client.post(
                f"{KITS_BASE}/voice-conversions",
                headers=headers,
                data={"voiceModelId": str(voice_model_id)},
                files={"soundFile": (audio_path.name, f, "application/octet-stream")},
            )
        if r.status_code >= 400:
            raise RuntimeError(f"Kits voice conversion failed: {r.status_code} {r.text[:400]}")
        job = r.json()
        job_id = job.get("id")
        if not job_id:
            raise RuntimeError("Kits did not return a conversion job ID")

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError("Kits voice conversion timed out")
        await asyncio.sleep(2)
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(f"{KITS_BASE}/voice-conversions/{job_id}", headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"Kits job lookup failed: {r.status_code} {r.text[:400]}")
        job = r.json()
        status = job.get("status")
        if status == "success":
            output_url = job.get("lossyOutputFileUrl") or job.get("outputFileUrl") or job.get("recombinedAudioFileUrl")
            if not output_url:
                raise RuntimeError("Kits conversion completed without an output URL")
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                audio = await client.get(output_url)
            if audio.status_code >= 400:
                raise RuntimeError(f"Could not download Kits output: {audio.status_code}")
            suffix = ".mp3" if job.get("lossyOutputFileUrl") else ".wav"
            out = OUTPUTS / f"kits_{uuid.uuid4().hex}{suffix}"
            out.write_bytes(audio.content)
            return out
        if status in {"error", "cancelled"}:
            raise RuntimeError(f"Kits conversion ended with status: {status}")
