from __future__ import annotations
import os, shutil, uuid, asyncio, secrets, hashlib, hmac
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import importlib.util
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from db import (init_db, add_history, list_history, upsert_voice, list_custom_voices, delete_voice,
                set_favorite, list_favorites, create_job, update_job, get_job, list_jobs,
                user_count, create_user, get_user_by_email, get_user, update_user_profile,
                create_session, get_session, delete_session, create_share, get_share, list_shares,
                set_catalog_override, list_catalog_overrides, admin_counts)
from audio_utils import OUTPUTS, save_upload, extract_audio, apply_audio_controls, demucs_two_stems, mix_tracks, pitch_shift, edit_audio, media_duration
from providers import (openai_tts, eleven_tts, eleven_voice_convert, eleven_sfx,
                       eleven_shared_voices, eleven_add_shared_voice,
                       respeecher_list_voices, respeecher_tts, speechify_list_voices, speechify_tts,
                       kits_list_voice_models, kits_voice_convert)
from catalog import search_catalog, load_catalog
from storage import status as storage_status, upload_file as storage_upload

DATA_DIR = Path(os.getenv("VOICELAB_DATA_DIR", str(Path(__file__).resolve().parent)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = Path(os.getenv("VOICELAB_ENV_FILE", str(DATA_DIR / ".env")))
load_dotenv(ENV_FILE)
app = FastAPI(title="VoiceLab Clone API", version="0.3.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",") if x.strip()]
origin_regex = os.getenv("CORS_ORIGIN_REGEX") or None
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_origin_regex=origin_regex, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
init_db()

OPENAI_VOICES = ["alloy","ash","ballad","coral","echo","fable","onyx","nova","sage","shimmer","verse","marin","cedar"]
BUILTINS = [
    {"id": f"openai-{v}", "name": v.title(), "category": "studio", "provider": "openai", "provider_voice_id": v, "gender": "Neutral", "description": "Built-in studio voice", "authorized": 1}
    for v in OPENAI_VOICES
]

class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    voice_id: str
    volume_db: float = Field(default=0, ge=-6, le=6)
    speed: float = Field(default=1, ge=0.5, le=2)
    emotion: str = "neutral"
    emotion_intensity: int = Field(default=50, ge=0, le=100)

class SFXRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    duration_seconds: float | None = Field(default=None, ge=0.5, le=22)

class VoiceRegistration(BaseModel):
    name: str
    category: Literal["character", "licensed", "custom", "studio"] = "custom"
    provider: Literal["openai", "elevenlabs", "respeecher", "speechify", "kits"]
    provider_voice_id: str
    gender: str = ""
    description: str = ""
    authorized: bool

class SharedVoiceImport(BaseModel):
    public_owner_id: str
    voice_id: str
    name: str
    category: Literal["character", "licensed", "custom", "studio"] = "custom"
    gender: str = ""
    description: str = "Imported from ElevenLabs shared Voice Library"

class SpeechifyVoiceImport(BaseModel):
    voice_id: str
    name: str
    category: Literal["character", "licensed", "custom", "studio"] = "licensed"
    gender: str = ""
    description: str = "Speechify shared voice"

class RespeecherVoiceImport(BaseModel):
    voice_id: str
    name: str
    category: Literal["character", "licensed", "custom", "studio"] = "custom"
    gender: str = ""
    description: str = "Licensed Respeecher voice"



class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)

class LoginRequest(BaseModel):
    email: str
    password: str

class ProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

class ShareRequest(BaseModel):
    output_url: str
    title: str = Field(default="VoiceLab clip", min_length=1, max_length=120)

class AudioEditRequest(BaseModel):
    output_url: str
    start_seconds: float = Field(default=0, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    gain_db: float = Field(default=0, ge=-24, le=24)
    fade_in: float = Field(default=0, ge=0, le=30)
    fade_out: float = Field(default=0, ge=0, le=30)

class StorageConfigRequest(BaseModel):
    backend: Literal["local", "s3"] = "local"
    bucket: str = ""
    region: str = ""
    endpoint_url: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    public_base_url: str = ""

class StorageUploadRequest(BaseModel):
    output_url: str

class CatalogOverrideRequest(BaseModel):
    enabled: bool = True
    note: str = ""

class FavoriteRequest(BaseModel):
    item_type: Literal["catalog", "voice"]
    item_id: str
    favorite: bool = True

class ProviderConfigRequest(BaseModel):
    provider: Literal["openai", "elevenlabs", "respeecher", "speechify", "kits", "voice_swap", "veritone"]
    api_key: str = Field(min_length=1)

PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "respeecher": "RESPEECHER_API_KEY",
    "speechify": "SPEECHIFY_API_KEY",
    "kits": "KITS_API_KEY",
    "voice_swap": "VOICE_SWAP_API_KEY",
    "veritone": "VERITONE_API_KEY",
}
class KitsVoiceImport(BaseModel):
    voice_id: str
    name: str
    category: Literal["character", "licensed", "custom", "studio"] = "licensed"
    gender: str = ""
    description: str = "Kits voice model"

PROVIDER_CAPABILITIES = {
    "openai": ["tts"],
    "elevenlabs": ["tts", "voice_conversion"],
    "respeecher": ["tts"],
    "speechify": ["tts"],
    "kits": ["voice_conversion"],
}

def with_capabilities(v: dict):
    item = dict(v)
    item["capabilities"] = PROVIDER_CAPABILITIES.get(item.get("provider"), [])
    return item

def get_voice(voice_id: str):
    for v in BUILTINS + list_custom_voices():
        if v["id"] == voice_id:
            return with_capabilities(v)
    raise HTTPException(404, "Voice not found")

def max_bytes():
    return int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024

def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 210_000).hex()

def _public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "display_name": u["display_name"], "is_admin": bool(u.get("is_admin")), "created_at": u.get("created_at")}

def _token_from_header(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()

def current_user_optional(authorization: str | None) -> dict | None:
    token=_token_from_header(authorization)
    if not token: return None
    sess=get_session(token)
    if not sess: return None
    try:
        if datetime.fromisoformat(sess["expires_at"]) < datetime.now(timezone.utc):
            delete_session(token); return None
    except Exception:
        return None
    return get_user(sess["user_id"])

def require_user(authorization: str | None) -> dict:
    u=current_user_optional(authorization)
    if not u: raise HTTPException(401, "Sign in required")
    return u

def require_admin(authorization: str | None) -> dict:
    u=require_user(authorization)
    if not u.get("is_admin"): raise HTTPException(403, "Admin access required")
    return u

def output_path_from_url(output_url: str) -> Path:
    prefix="/api/files/"
    if not output_url.startswith(prefix): raise HTTPException(400, "Only local VoiceLab outputs can be used here")
    name=Path(output_url[len(prefix):]).name
    path=OUTPUTS/name
    if not path.exists(): raise HTTPException(404, "Output file not found")
    return path

def _write_env_values(values: dict[str,str]):
    env_path=ENV_FILE
    lines=env_path.read_text().splitlines() if env_path.exists() else []
    keys=set(values); out=[]; seen=set()
    for line in lines:
        key=line.split("=",1)[0] if "=" in line else ""
        if key in keys:
            out.append(f"{key}={values[key]}"); seen.add(key)
        else: out.append(line)
    for key,val in values.items():
        if key not in seen: out.append(f"{key}={val}")
        os.environ[key]=val
    env_path.write_text("\n".join(out).rstrip()+"\n")

async def read_upload(file: UploadFile):
    data = await file.read()
    if len(data) > max_bytes():
        raise HTTPException(413, f"Upload exceeds {os.getenv('MAX_UPLOAD_MB','20')} MB")
    return data

def url_for(path: Path):
    return f"/api/files/{path.name}"

@app.get("/api/health")
def health():
    return {"ok": True, "ffmpeg": shutil.which("ffmpeg") is not None, "demucs": importlib.util.find_spec("demucs") is not None, "providers": {"openai": bool(os.getenv("OPENAI_API_KEY")), "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")), "respeecher": bool(os.getenv("RESPEECHER_API_KEY")), "speechify": bool(os.getenv("SPEECHIFY_API_KEY")), "voice_swap": bool(os.getenv("VOICE_SWAP_API_KEY")), "kits": bool(os.getenv("KITS_API_KEY")), "veritone": bool(os.getenv("VERITONE_API_KEY"))}}

@app.get("/api/voices")
def voices(category: str | None = None):
    items = [with_capabilities(v) for v in BUILTINS + [v for v in list_custom_voices() if v.get("authorized")]]
    if category:
        items = [v for v in items if v["category"] == category]
    return items

@app.post("/api/voices")
def register_voice(v: VoiceRegistration):
    if not v.authorized:
        raise HTTPException(400, "Only voices you are authorized to use may be registered")
    item = {
        "id": f"custom-{uuid.uuid4().hex[:12]}", "name": v.name, "category": v.category,
        "provider": v.provider, "provider_voice_id": v.provider_voice_id,
        "gender": v.gender, "description": v.description, "authorized": 1,
    }
    upsert_voice(item)
    return with_capabilities(item)


@app.get("/api/catalog")
def catalog(q: str = "", provider: str = "", kind: str = "", access: str = "", capability: str = ""):
    items=search_catalog(q=q, provider=provider, kind=kind, access=access, capability=capability)
    overrides=list_catalog_overrides()
    out=[]
    for item in items:
        ov=overrides.get(item.get("id"), {})
        if ov.get("enabled", 1) == 0:
            continue
        x=dict(item); x["admin_note"]=ov.get("note", ""); out.append(x)
    return out

@app.get("/api/catalog/live/elevenlabs")
async def catalog_live_elevenlabs(search: str = "", category: str = "professional", page_size: int = 50):
    try:
        data = await eleven_shared_voices(search=search, category=category, page_size=page_size)
        return data
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/catalog/import/elevenlabs")
async def import_elevenlabs_voice(v: SharedVoiceImport):
    try:
        provider_voice_id = await eleven_add_shared_voice(v.public_owner_id, v.voice_id, v.name)
        item = {
            "id": f"custom-{uuid.uuid4().hex[:12]}", "name": v.name, "category": v.category,
            "provider": "elevenlabs", "provider_voice_id": provider_voice_id,
            "gender": v.gender, "description": v.description, "authorized": 1,
        }
        upsert_voice(item)
        return item
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/catalog/live/respeecher")
async def catalog_live_respeecher():
    try:
        return await respeecher_list_voices()
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/catalog/import/respeecher")
def import_respeecher_voice(v: RespeecherVoiceImport):
    item = {
        "id": f"custom-{uuid.uuid4().hex[:12]}", "name": v.name, "category": v.category,
        "provider": "respeecher", "provider_voice_id": v.voice_id,
        "gender": v.gender, "description": v.description, "authorized": 1,
    }
    upsert_voice(item)
    return item


@app.get("/api/catalog/live/speechify")
async def catalog_live_speechify(locale: str = "en", limit: int = 100):
    try:
        return await speechify_list_voices(limit=limit, locale=locale)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/catalog/import/speechify")
def import_speechify_voice(v: SpeechifyVoiceImport):
    item = {
        "id": f"custom-{uuid.uuid4().hex[:12]}", "name": v.name, "category": v.category,
        "provider": "speechify", "provider_voice_id": v.voice_id,
        "gender": v.gender, "description": v.description, "authorized": 1,
    }
    upsert_voice(item)
    return item

@app.get("/api/catalog/live/kits")
async def catalog_live_kits(page: int = 1, per_page: int = 50, my_models: bool = False):
    try:
        return await kits_list_voice_models(page=page, per_page=per_page, my_models=my_models)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/catalog/import/kits")
def import_kits_voice(v: KitsVoiceImport):
    item = {
        "id": f"custom-{uuid.uuid4().hex[:12]}", "name": v.name, "category": v.category,
        "provider": "kits", "provider_voice_id": v.voice_id,
        "gender": v.gender, "description": v.description, "authorized": 1,
    }
    upsert_voice(item)
    return with_capabilities(item)


@app.get("/api/favorites")
def favorites(item_type: str | None = None):
    return list_favorites(item_type)

@app.post("/api/favorites")
def favorite(req: FavoriteRequest):
    set_favorite(req.item_type, req.item_id, req.favorite)
    return {"ok": True, "favorite": req.favorite}

@app.get("/api/providers/status")
def provider_status():
    return {
        name: {"configured": bool(os.getenv(env_name)), "env_key": env_name}
        for name, env_name in PROVIDER_ENV_KEYS.items()
    }

@app.post("/api/providers/configure")
def configure_provider(req: ProviderConfigRequest):
    env_name = PROVIDER_ENV_KEYS[req.provider]
    value = req.api_key.strip()
    if not value:
        raise HTTPException(400, "API key cannot be empty")
    env_path = Path(__file__).with_name(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    replaced = False
    out = []
    for line in lines:
        if line.startswith(env_name + "="):
            out.append(f"{env_name}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{env_name}={value}")
    env_path.write_text("\n".join(out).rstrip() + "\n")
    os.environ[env_name] = value
    return {"ok": True, "provider": req.provider, "configured": True}

@app.delete("/api/providers/{provider}")
def remove_provider(provider: str):
    if provider not in PROVIDER_ENV_KEYS:
        raise HTTPException(404, "Unknown provider")
    env_name = PROVIDER_ENV_KEYS[provider]
    env_path = Path(__file__).with_name(".env")
    if env_path.exists():
        lines = [line for line in env_path.read_text().splitlines() if not line.startswith(env_name + "=")]
        env_path.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""))
    os.environ.pop(env_name, None)
    return {"ok": True, "provider": provider, "configured": False}

@app.get("/api/jobs")
def jobs(limit: int = 25):
    return list_jobs(limit)

@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    item = get_job(job_id)
    if not item:
        raise HTTPException(404, "Job not found")
    return item

async def _run_tts_job(job_id: str, req: TTSRequest):
    try:
        update_job(job_id, status="running", progress=10, phase="Preparing voice")
        v = get_voice(req.voice_id)
        if "tts" not in v.get("capabilities", []):
            raise RuntimeError(f"{v['provider']} voice does not support text-to-speech")
        instructions = f"Speak with a {req.emotion} emotional tone. Intensity {req.emotion_intensity} out of 100."
        update_job(job_id, progress=28, phase=f"Generating with {v['provider']}")
        if v["provider"] == "openai":
            raw = await openai_tts(req.text, v["provider_voice_id"], req.speed, instructions)
            update_job(job_id, progress=78, phase="Mastering audio")
            out = await asyncio.to_thread(apply_audio_controls, raw, req.volume_db, 1.0)
        elif v["provider"] == "elevenlabs":
            raw = await eleven_tts(req.text, v["provider_voice_id"])
            update_job(job_id, progress=78, phase="Mastering audio")
            out = await asyncio.to_thread(apply_audio_controls, raw, req.volume_db, req.speed)
        elif v["provider"] == "respeecher":
            raw = await respeecher_tts(req.text, v["provider_voice_id"])
            update_job(job_id, progress=78, phase="Mastering audio")
            out = await asyncio.to_thread(apply_audio_controls, raw, req.volume_db, req.speed)
        elif v["provider"] == "speechify":
            raw = await speechify_tts(req.text, v["provider_voice_id"])
            update_job(job_id, progress=78, phase="Mastering audio")
            out = await asyncio.to_thread(apply_audio_controls, raw, req.volume_db, req.speed)
        else:
            raise RuntimeError("Unsupported provider")
        add_history("tts", f"TTS · {v['name']}", str(out), {"voice": v["name"], "text": req.text[:200], "ai_generated": True})
        update_job(job_id, status="completed", progress=100, phase="Ready", output_url=url_for(out))
    except Exception as e:
        update_job(job_id, status="failed", phase="Failed", error=str(e))

@app.post("/api/jobs/tts")
async def queue_tts(req: TTSRequest):
    v = get_voice(req.voice_id)
    job_id = uuid.uuid4().hex
    create_job(job_id, "tts", f"TTS · {v['name']}", {"voice": v["name"]})
    asyncio.create_task(_run_tts_job(job_id, req))
    return get_job(job_id)

async def _run_sfx_job(job_id: str, req: SFXRequest):
    try:
        update_job(job_id, status="running", progress=18, phase="Generating sound")
        out = await eleven_sfx(req.prompt, req.duration_seconds)
        add_history("sfx", "Sound effect", str(out), {"prompt": req.prompt})
        update_job(job_id, status="completed", progress=100, phase="Ready", output_url=url_for(out))
    except Exception as e:
        update_job(job_id, status="failed", phase="Failed", error=str(e))

@app.post("/api/jobs/sfx")
async def queue_sfx(req: SFXRequest):
    job_id = uuid.uuid4().hex
    create_job(job_id, "sfx", "Sound effect", {"prompt": req.prompt[:120]})
    asyncio.create_task(_run_sfx_job(job_id, req))
    return get_job(job_id)

async def _run_file_job(job_id: str, kind: str, src: Path, original_name: str, format: str = "mp3"):
    try:
        if kind == "extract":
            update_job(job_id, status="running", progress=24, phase="Extracting audio")
            out = await asyncio.to_thread(extract_audio, src, "wav" if format == "wav" else "mp3")
            add_history("extract", f"Extract · {original_name}", str(out), {})
        else:
            update_job(job_id, status="running", progress=15, phase="Separating stems")
            vocals, inst = await asyncio.to_thread(demucs_two_stems, src)
            update_job(job_id, progress=82, phase="Finalizing audio")
            if kind == "isolate":
                out = OUTPUTS / f"vocals_{uuid.uuid4().hex}.wav"
                await asyncio.to_thread(shutil.copy2, vocals, out)
                add_history("isolate", f"Vocals · {original_name}", str(out), {})
            else:
                out = OUTPUTS / f"instrumental_{uuid.uuid4().hex}.wav"
                await asyncio.to_thread(shutil.copy2, inst, out)
                add_history("remove-vocals", f"Instrumental · {original_name}", str(out), {})
        update_job(job_id, status="completed", progress=100, phase="Ready", output_url=url_for(out))
    except Exception as e:
        update_job(job_id, status="failed", phase="Failed", error=str(e))

@app.post("/api/jobs/audio/{kind}")
async def queue_audio_job(kind: str, file: UploadFile = File(...), format: str = Form("mp3")):
    if kind not in {"extract", "isolate", "remove-vocals"}:
        raise HTTPException(404, "Unknown audio job")
    data = await read_upload(file)
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    src = save_upload(data, suffix)
    title_map = {"extract": "Audio extraction", "isolate": "Vocal isolation", "remove-vocals": "Vocal removal"}
    job_id = uuid.uuid4().hex
    create_job(job_id, kind, title_map[kind], {"source": file.filename})
    asyncio.create_task(_run_file_job(job_id, kind, src, file.filename or "upload", format))
    return get_job(job_id)

async def _run_convert_job(job_id: str, src: Path, v: dict, source_name: str):
    try:
        update_job(job_id, status="running", progress=18, phase=f"Converting with {v['provider']}")
        if v["provider"] == "elevenlabs":
            out = await eleven_voice_convert(src, v["provider_voice_id"])
        elif v["provider"] == "kits":
            update_job(job_id, progress=35, phase="Kits conversion queued")
            out = await kits_voice_convert(src, v["provider_voice_id"])
        else:
            raise RuntimeError("Unsupported voice-conversion provider")
        add_history("voice-convert", f"Voice conversion · {v['name']}", str(out), {"voice": v["name"], "source": source_name, "provider": v["provider"], "ai_generated": True})
        update_job(job_id, status="completed", progress=100, phase="Ready", output_url=url_for(out))
    except Exception as e:
        update_job(job_id, status="failed", phase="Failed", error=str(e))

@app.post("/api/jobs/voice-convert")
async def queue_voice_convert(file: UploadFile = File(...), voice_id: str = Form(...)):
    v = get_voice(voice_id)
    if "voice_conversion" not in v.get("capabilities", []):
        raise HTTPException(400, "Selected voice does not support voice-to-voice conversion")
    data = await read_upload(file)
    src = save_upload(data, Path(file.filename or "recording.wav").suffix or ".wav")
    job_id = uuid.uuid4().hex
    create_job(job_id, "voice-convert", f"Voice conversion · {v['name']}", {"voice": v["name"], "source": file.filename})
    asyncio.create_task(_run_convert_job(job_id, src, v, file.filename or "recording"))
    return get_job(job_id)

async def _run_cover_job(job_id: str, src: Path, v: dict, source_name: str, pitch_semitones: float = 0, vocal_gain_db: float = 0, instrumental_gain_db: float = 0):
    try:
        update_job(job_id, status="running", progress=8, phase="Separating vocals and instrumental")
        vocals, inst = await asyncio.to_thread(demucs_two_stems, src)
        update_job(job_id, progress=42, phase=f"Converting vocals with {v['provider']}")
        if v["provider"] == "elevenlabs":
            converted = await eleven_voice_convert(vocals, v["provider_voice_id"])
        elif v["provider"] == "kits":
            converted = await kits_voice_convert(vocals, v["provider_voice_id"])
        else:
            raise RuntimeError("Unsupported cover voice provider")
        if abs(pitch_semitones) > 0.001:
            update_job(job_id, progress=72, phase=f"Transposing vocals {pitch_semitones:+.1f} semitones")
            converted = await asyncio.to_thread(pitch_shift, converted, pitch_semitones)
        update_job(job_id, progress=84, phase="Remixing cover")
        out = await asyncio.to_thread(mix_tracks, inst, converted, instrumental_gain_db, vocal_gain_db)
        add_history("cover", f"Cover · {v['name']}", str(out), {"voice": v["name"], "source": source_name, "provider": v["provider"], "pitch_semitones": pitch_semitones, "vocal_gain_db": vocal_gain_db, "instrumental_gain_db": instrumental_gain_db, "ai_generated": True})
        update_job(job_id, status="completed", progress=100, phase="Ready", output_url=url_for(out))
    except Exception as e:
        update_job(job_id, status="failed", phase="Failed", error=str(e))

@app.post("/api/jobs/cover")
async def queue_cover(file: UploadFile = File(...), voice_id: str = Form(...), pitch_semitones: float = Form(0), vocal_gain_db: float = Form(0), instrumental_gain_db: float = Form(0)):
    v = get_voice(voice_id)
    if "voice_conversion" not in v.get("capabilities", []):
        raise HTTPException(400, "AI Cover requires a voice-conversion-capable voice")
    data = await read_upload(file)
    src = save_upload(data, Path(file.filename or "song.mp3").suffix or ".mp3")
    job_id = uuid.uuid4().hex
    create_job(job_id, "cover", f"Cover · {v['name']}", {"voice": v["name"], "source": file.filename, "pitch_semitones": pitch_semitones})
    asyncio.create_task(_run_cover_job(job_id, src, v, file.filename or "song", pitch_semitones, vocal_gain_db, instrumental_gain_db))
    return get_job(job_id)

@app.post("/api/tts")
async def tts(req: TTSRequest):
    v = get_voice(req.voice_id)
    if "tts" not in v.get("capabilities", []):
        raise HTTPException(400, f"{v['provider']} voice does not support text-to-speech in this build")
    try:
        instructions = f"Speak with a {req.emotion} emotional tone. Intensity {req.emotion_intensity} out of 100."
        if v["provider"] == "openai":
            raw = await openai_tts(req.text, v["provider_voice_id"], req.speed, instructions)
            out = apply_audio_controls(raw, req.volume_db, 1.0)
        elif v["provider"] == "elevenlabs":
            raw = await eleven_tts(req.text, v["provider_voice_id"])
            out = apply_audio_controls(raw, req.volume_db, req.speed)
        elif v["provider"] == "respeecher":
            raw = await respeecher_tts(req.text, v["provider_voice_id"])
            out = apply_audio_controls(raw, req.volume_db, req.speed)
        elif v["provider"] == "speechify":
            raw = await speechify_tts(req.text, v["provider_voice_id"])
            out = apply_audio_controls(raw, req.volume_db, req.speed)
        else:
            raise RuntimeError("Unsupported provider")
        add_history("tts", f"TTS · {v['name']}", str(out), {"voice": v["name"], "text": req.text[:200], "ai_generated": True})
        return {"audio_url": url_for(out), "disclosure": "AI-generated voice"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/sfx")
async def sfx(req: SFXRequest):
    try:
        out = await eleven_sfx(req.prompt, req.duration_seconds)
        add_history("sfx", "Sound effect", str(out), {"prompt": req.prompt})
        return {"audio_url": url_for(out)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/audio/extract")
async def audio_extract(file: UploadFile = File(...), format: str = Form("mp3")):
    data = await read_upload(file)
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    src = save_upload(data, suffix)
    try:
        out = extract_audio(src, "wav" if format == "wav" else "mp3")
        add_history("extract", f"Extract · {file.filename}", str(out), {})
        return {"audio_url": url_for(out)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/audio/isolate")
async def isolate(file: UploadFile = File(...)):
    data = await read_upload(file)
    src = save_upload(data, Path(file.filename or "audio.mp3").suffix or ".mp3")
    try:
        vocals, _ = demucs_two_stems(src)
        out = OUTPUTS / f"vocals_{uuid.uuid4().hex}.wav"; shutil.copy2(vocals, out)
        add_history("isolate", f"Vocals · {file.filename}", str(out), {})
        return {"audio_url": url_for(out)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/audio/remove-vocals")
async def remove_vocals(file: UploadFile = File(...)):
    data = await read_upload(file)
    src = save_upload(data, Path(file.filename or "audio.mp3").suffix or ".mp3")
    try:
        _, inst = demucs_two_stems(src)
        out = OUTPUTS / f"instrumental_{uuid.uuid4().hex}.wav"; shutil.copy2(inst, out)
        add_history("remove-vocals", f"Instrumental · {file.filename}", str(out), {})
        return {"audio_url": url_for(out)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/voice-convert")
async def voice_convert(file: UploadFile = File(...), voice_id: str = Form(...)):
    v = get_voice(voice_id)
    if "voice_conversion" not in v.get("capabilities", []):
        raise HTTPException(400, "Selected voice does not support voice-to-voice conversion")
    data = await read_upload(file)
    src = save_upload(data, Path(file.filename or "recording.wav").suffix or ".wav")
    try:
        if v["provider"] == "elevenlabs":
            out = await eleven_voice_convert(src, v["provider_voice_id"])
        elif v["provider"] == "kits":
            out = await kits_voice_convert(src, v["provider_voice_id"])
        else:
            raise RuntimeError("Unsupported voice-conversion provider")
        add_history("voice-convert", f"Voice conversion · {v['name']}", str(out), {"voice": v["name"], "source": file.filename, "provider": v["provider"], "ai_generated": True})
        return {"audio_url": url_for(out), "disclosure": "AI-generated/converted voice"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/cover")
async def cover(file: UploadFile = File(...), voice_id: str = Form(...)):
    v = get_voice(voice_id)
    if "voice_conversion" not in v.get("capabilities", []):
        raise HTTPException(400, "AI Cover requires a voice-conversion-capable voice")
    data = await read_upload(file)
    src = save_upload(data, Path(file.filename or "song.mp3").suffix or ".mp3")
    try:
        vocals, inst = demucs_two_stems(src)
        if v["provider"] == "elevenlabs":
            converted = await eleven_voice_convert(vocals, v["provider_voice_id"])
        elif v["provider"] == "kits":
            converted = await kits_voice_convert(vocals, v["provider_voice_id"])
        else:
            raise RuntimeError("Unsupported cover voice provider")
        out = mix_tracks(inst, converted)
        add_history("cover", f"Cover · {v['name']}", str(out), {"voice": v["name"], "source": file.filename, "provider": v["provider"], "ai_generated": True})
        return {"audio_url": url_for(out), "disclosure": "AI-generated/converted voice"}
    except Exception as e:
        raise HTTPException(500, str(e))

# --- Local accounts / profiles ---
@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    if "@" not in req.email: raise HTTPException(400, "Enter a valid email address")
    if get_user_by_email(req.email): raise HTTPException(409, "An account with that email already exists")
    uid=uuid.uuid4().hex; salt=secrets.token_hex(16); first=user_count()==0
    create_user(uid,req.email,req.display_name,_hash_password(req.password,salt),salt,first)
    token=secrets.token_urlsafe(32); expires=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(); create_session(token,uid,expires)
    return {"token":token,"user":_public_user(get_user(uid))}

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    u=get_user_by_email(req.email)
    if not u or not hmac.compare_digest(_hash_password(req.password,u["salt"]),u["password_hash"]): raise HTTPException(401,"Invalid email or password")
    token=secrets.token_urlsafe(32); expires=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(); create_session(token,u["id"],expires)
    return {"token":token,"user":_public_user(u)}

@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None)):
    return _public_user(require_user(authorization))

@app.patch("/api/auth/profile")
def auth_profile(req: ProfileRequest, authorization: str | None = Header(default=None)):
    u=require_user(authorization); update_user_profile(u["id"],req.display_name); return _public_user(get_user(u["id"]))

@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = Header(default=None)):
    token=_token_from_header(authorization)
    if token: delete_session(token)
    return {"ok":True}

# --- Shareable generated clips ---
@app.post("/api/shares")
def share_create(req: ShareRequest, authorization: str | None = Header(default=None)):
    path=output_path_from_url(req.output_url); u=current_user_optional(authorization); token=secrets.token_urlsafe(10)
    create_share(token,req.title,path.name,u["id"] if u else None)
    return {"token":token,"share_url":f"/share/{token}","audio_url":f"/api/files/{path.name}"}

@app.get("/api/shares/{token}")
def share_info(token: str):
    s=get_share(token)
    if not s: raise HTTPException(404,"Share not found")
    path=OUTPUTS/Path(s["filename"]).name
    if not path.exists(): raise HTTPException(404,"Shared audio no longer exists")
    return {**s,"audio_url":f"/api/files/{path.name}","disclosure":"AI-generated or processed audio"}

@app.get("/share/{token}", response_class=HTMLResponse)
def share_page(token: str):
    s=get_share(token)
    if not s: raise HTTPException(404,"Share not found")
    path=OUTPUTS/Path(s["filename"]).name
    if not path.exists(): raise HTTPException(404,"Shared audio no longer exists")
    title=(s["title"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
    audio=f"/api/files/{path.name}"
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>{title} · VoiceLab</title><style>body{{margin:0;background:#090b11;color:#fff;font-family:system-ui;display:grid;place-items:center;min-height:100vh}}main{{width:min(680px,90vw);background:#11141d;border:1px solid #292d3a;border-radius:20px;padding:28px}}h1{{margin:0 0 8px}}p{{color:#9298aa}}audio{{width:100%;margin:20px 0}}small{{color:#7d8394}}</style></head><body><main><small>VoiceLab shared clip · AI-generated/processed audio</small><h1>{title}</h1><p>Shared from VoiceLab Studio.</p><audio controls autoplay src='{audio}'></audio><a href='{audio}' download style='color:#bda8ff'>Download audio</a></main></body></html>""")

# --- Waveform editor ---
@app.post("/api/audio/edit")
async def audio_edit(req: AudioEditRequest):
    src=output_path_from_url(req.output_url)
    try:
        out=await asyncio.to_thread(edit_audio,src,req.start_seconds,req.end_seconds,req.gain_db,req.fade_in,req.fade_out)
        add_history("edit","Edited audio",str(out),{"source":src.name,"start":req.start_seconds,"end":req.end_seconds,"gain_db":req.gain_db,"fade_in":req.fade_in,"fade_out":req.fade_out})
        return {"audio_url":url_for(out),"duration":media_duration(out)}
    except Exception as e: raise HTTPException(500,str(e))

@app.get("/api/audio/info/{name}")
def audio_info(name: str):
    path=OUTPUTS/Path(name).name
    if not path.exists(): raise HTTPException(404,"File not found")
    try: return {"duration":media_duration(path),"filename":path.name}
    except Exception as e: raise HTTPException(500,str(e))

# --- Optional S3-compatible cloud storage ---
@app.get("/api/storage/status")
def storage_get_status(): return storage_status()

@app.post("/api/storage/configure")
def storage_configure(req: StorageConfigRequest, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    vals={"STORAGE_BACKEND":req.backend,"S3_BUCKET":req.bucket,"S3_REGION":req.region,"S3_ENDPOINT_URL":req.endpoint_url,"AWS_ACCESS_KEY_ID":req.access_key_id,"AWS_SECRET_ACCESS_KEY":req.secret_access_key,"S3_PUBLIC_BASE_URL":req.public_base_url}
    _write_env_values(vals); return storage_status()

@app.post("/api/storage/upload")
def storage_upload_output(req: StorageUploadRequest, authorization: str | None = Header(default=None)):
    require_user(authorization); path=output_path_from_url(req.output_url)
    try: return storage_upload(path)
    except Exception as e: raise HTTPException(500,str(e))

# --- Admin ---
@app.get("/api/admin/summary")
def admin_summary(authorization: str | None = Header(default=None)):
    require_admin(authorization); return {**admin_counts(),"providers":provider_status(),"storage":storage_status()}

@app.get("/api/admin/catalog")
def admin_catalog(authorization: str | None = Header(default=None)):
    require_admin(authorization); ovs=list_catalog_overrides(); out=[]
    for x in load_catalog():
        y=dict(x); ov=ovs.get(x.get("id"),{}); y["enabled"]=bool(ov.get("enabled",1)); y["admin_note"]=ov.get("note",""); out.append(y)
    return out

@app.patch("/api/admin/catalog/{item_id}")
def admin_catalog_update(item_id: str, req: CatalogOverrideRequest, authorization: str | None = Header(default=None)):
    require_admin(authorization); set_catalog_override(item_id,req.enabled,req.note); return {"ok":True,"item_id":item_id,"enabled":req.enabled}

@app.delete("/api/admin/voices/{voice_id}")
def admin_delete_voice(voice_id: str, authorization: str | None = Header(default=None)):
    require_admin(authorization); delete_voice(voice_id); return {"ok":True}

@app.get("/api/admin/shares")
def admin_shares(authorization: str | None = Header(default=None)):
    require_admin(authorization); return list_shares(100)

@app.get("/api/history")
def history(limit: int = 50, authorization: str | None = Header(default=None)):
    u=current_user_optional(authorization)
    return list_history(limit, u["id"] if u else None)

@app.get("/api/files/{name}")
def files(name: str):
    path = OUTPUTS / Path(name).name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name)

# Serve the bundled frontend last so /api/* routes keep precedence.
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
