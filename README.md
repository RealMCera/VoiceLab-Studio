# VoiceLab Studio

VoiceLab Studio is an original, full-stack AI voice workspace inspired by the workflow and tool breadth of modern AI voice sites. It does **not** copy AIVoiceLab source code, branding, proprietary assets, or unauthorized celebrity voice models.

## What is included

- AI text-to-speech with searchable voices, speed, volume, emotion and intensity controls
- Voice-to-voice conversion from uploaded or microphone-recorded audio
- Studio, Character and Licensed Voice views
- **Voice Marketplace** with a researched catalog of licensed / rights-holder-approved sources
- Live provider catalog sync and one-click local registration for supported providers
- AI Cover pipeline: Demucs vocal separation → authorized voice conversion → FFmpeg remix
- AI sound-effect generation
- Vocal isolator and vocal remover
- Video/audio extractor
- Downloadable outputs, waveform previews, and persistent local history
- Persistent favorites, advanced marketplace filters, and a real server-side generation queue
- Provider Setup screen for connecting/disconnecting API keys without editing files
- Responsive desktop/mobile UI
- Windows bootstrap launcher and Docker support

## Voice Marketplace

The bundled research catalog currently contains **88 entries** across:

- ElevenLabs Iconic Marketplace
- ElevenLabs shared Voice Library
- Respeecher
- Speechify
- Voice-Swap
- Kits AI
- Veritone Voice

The Marketplace separates voices by access status rather than pretending every famous voice is instantly available:

- `provider_account` — usable when your provider account/license grants access
- `request_license` — requires rights-holder/project approval
- `enterprise` — requires enterprise/provider onboarding

### Live sync currently implemented

- **ElevenLabs** shared Professional Voice Clones
- **Respeecher** licensed TTS voices
- **Speechify** shared voices
- **Kits AI** voice models

These calls happen server-side. Provider API keys never go to the browser. The Settings page can write or replace local keys in `apps/api/.env` for you.

## Working provider adapters

- **OpenAI** — TTS
- **ElevenLabs** — TTS, shared Voice Library import, speech-to-speech voice conversion, sound effects
- **Respeecher** — licensed voice discovery + TTS
- **Speechify** — shared voice discovery + TTS
- **Kits AI** — voice-model discovery + voice conversion; also usable in the AI Cover pipeline
- **Demucs** — local vocal/instrumental separation
- **FFmpeg** — local extraction, processing and remixing

Voice-Swap and Veritone are catalogued because they offer rights-managed/licensed voice services and APIs, but this build does not guess private/enterprise endpoints or credentials. Their adapters can be added when the account/API access is available.

## Windows setup

### Requirements

1. Python 3.11+
2. FFmpeg in PATH
3. At least one provider API key for AI generation

Then double-click:

`start-windows.bat`

The launcher creates the Python virtual environment, installs dependencies, starts FastAPI, and opens the app. No Node/npm setup is required.

App: `http://localhost:8000`

API docs: `http://localhost:8000/docs`


## Netlify + Render deployment

This build is deployment-ready for a split production setup:

- **Netlify** hosts the static frontend in `apps/web`.
- **Render** hosts the Dockerized FastAPI, FFmpeg, Demucs, SQLite, uploads, and generated media.

`netlify.toml` runs `scripts/netlify-config.mjs`, which writes the public backend URL into `apps/web/config.js` from the Netlify environment variable `VOICELAB_API_BASE`. Only the backend URL belongs in the Netlify frontend environment; provider API keys stay on the backend.

The backend now supports `VOICELAB_DATA_DIR` and `VOICELAB_ENV_FILE` so a Render persistent disk mounted at `/data` can preserve the database, accounts, jobs, uploads, outputs, and server-managed provider settings across deploys. The Docker image also honors Render's `PORT` environment variable.

See **`NETLIFY_DEPLOY.md`** for the exact deployment sequence.

## API keys

On first launch, the starter creates `apps/api/.env` from `.env.example`.

```env
OPENAI_API_KEY=
OPENAI_TTS_MODEL=gpt-4o-mini-tts
ELEVENLABS_API_KEY=
RESPEECHER_API_KEY=
SPEECHIFY_API_KEY=
KITS_API_KEY=
VOICE_SWAP_API_KEY=
VERITONE_API_KEY=
MAX_UPLOAD_MB=20
CORS_ORIGINS=http://localhost:8000
```

Only configure providers you actually use.

## Adding voices

There are two paths:

1. Open **Marketplace** and use a supported live-sync button. Voices returned by your own provider account can be added to the local Voice Library.
2. Open **Voice Library** and manually register a provider voice ID you own or are authorized to use.

The app intentionally does not bundle random scraped public-figure models. Celebrity/iconic listings that require approval remain marked as approval-required and link back to the rights-managed provider.

## TTS vs conversion-only models

The UI tracks provider capabilities. For example:

- OpenAI / Respeecher / Speechify voices are currently TTS-capable in this build.
- ElevenLabs voices can support TTS and voice conversion.
- Kits models are treated as voice-conversion models, not TTS voices.

That prevents a conversion-only model from appearing as though it can generate text directly.

## AI Cover

AI Cover accepts an authorized ElevenLabs or Kits conversion voice:

1. Demucs separates vocals and instrumental.
2. The isolated vocal is sent to the selected authorized conversion provider.
3. FFmpeg remixes the converted vocal with the instrumental.

Use only audio and target voices you have the rights or permission to process.

## Research exports

- `VOICE_CATALOG.csv` — spreadsheet-friendly master list
- `VOICE_CATALOG.md` — readable provider summary
- `apps/api/voice_catalog.json` — catalog used directly by the app

## Generation queue and progress

Long-running tools now use a SQLite-backed server-side job queue. The UI receives a job immediately, then polls real status fields such as `queued`, `running`, `completed`, `failed`, percentage, and current phase. This is used by TTS, sound effects, extraction, stem separation, voice conversion, and AI Cover.

## Favorites and waveforms

Marketplace entries and usable voices can be favorited and the preference survives restarts. Generated audio and History items include waveform previews drawn in the browser with the Web Audio API.

## Provider Setup

Open **Settings** to connect, replace, or disconnect supported provider API keys. Keys are POSTed only to the local FastAPI server, written to `apps/api/.env`, placed into the server process environment, and never returned to the browser.

## Future production upgrades

- PostgreSQL for multi-instance account/job persistence
- Redis/Celery or another distributed queue for horizontal scaling
- WebSocket/SSE progress instead of polling
- Provider-specific usage/cost meters and quotas
- Signed media retention/cleanup policies
- Voice preview caching/CDN delivery
- License/approval records per imported voice
- Email verification, password reset, rate limiting, and hardened public-SaaS authentication

## Responsible voice use

Only generate with voices you own, licensed voices, or voices for which the speaker/rights holder has given the required permission. Keep generated speech clearly disclosed as synthetic when it could reasonably be mistaken for an authentic recording.

## Product Suite Upgrade (v0.3)

VoiceLab now includes a second product layer on top of the generation tools:

- **Local accounts and profiles** — register, sign in, update your display name, and maintain a 30-day local session. The first account created becomes the workspace administrator.
- **Shareable clips** — History can create a public `/share/<token>` landing page with playback, disclosure, and download.
- **A/B Voice Compare** — choose two TTS-capable voices and generate the same script with both at the same time.
- **Audio Editor** — choose any generated clip and export a new version with trim start/end, gain, fade-in, and fade-out controls.
- **Advanced AI Cover mix** — transpose converted vocals from -12 to +12 semitones and independently change converted-vocal and instrumental levels before remixing.
- **Admin panel** — view workspace counts, enable/disable researched catalog entries, and configure object storage.
- **S3-compatible cloud mirroring** — optional upload support for AWS S3, Cloudflare R2, Backblaze B2 S3, MinIO, or another compatible endpoint. Local storage remains the default.

### Accounts

Accounts are intentionally local in this self-hosted build. Passwords are never stored in plaintext: the backend uses PBKDF2-HMAC-SHA256 with a random per-account salt. Session tokens are random server-side records stored in SQLite.

The current account layer is a self-hosted workspace feature, not a hardened public SaaS identity system. Before exposing a deployment to untrusted public users, add email verification, password reset, rate limiting, CSRF strategy where applicable, audit logging, and production-grade secret/session management.

### Cloud storage

Administrators can switch the storage backend from Local to S3-compatible in **Admin → Cloud storage**. Configure:

```env
STORAGE_BACKEND=s3
S3_BUCKET=
S3_REGION=
S3_ENDPOINT_URL=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_PUBLIC_BASE_URL=
```

`S3_ENDPOINT_URL` is optional for AWS S3 and useful for S3-compatible services. `S3_PUBLIC_BASE_URL` is optional. When it is omitted, VoiceLab generates a temporary presigned download URL after an upload.

Cloud upload buttons appear in History for signed-in users after storage is configured.

### Share links

A generated share URL looks like:

```text
http://localhost:8000/share/<random-token>
```

On a local-only install, that link is reachable only from machines that can reach your VoiceLab server. On a hosted deployment, it becomes a normal externally shareable URL.
