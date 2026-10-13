# Deploy VoiceLab Studio with Netlify + Render

VoiceLab is split into two deployment targets:

- **Netlify:** the static `apps/web` frontend.
- **Render:** the Dockerized FastAPI + FFmpeg + Demucs backend.

This split is intentional. Large uploads and audio processing go directly from the browser to Render instead of through Netlify Functions.

## 1. Put this project in GitHub

Create a repository containing the project root (including `netlify.toml`, `render.yaml`, and `Dockerfile`). Do not commit `apps/api/.env`, provider API keys, the SQLite database, uploads, or generated outputs.

## 2. Deploy the backend on Render

In Render, create a Blueprint from the repository (using `render.yaml`) or create a Docker Web Service manually. The Dockerfile installs FFmpeg and the Python dependencies.

Use a paid service with enough RAM/CPU for Demucs. The Blueprint expects a persistent disk mounted at `/data`; this preserves accounts, jobs, favorites, generated files, and the SQLite database across deploys.

Set provider secrets in Render, not in GitHub. At minimum set only the providers you plan to use.

After deploy, copy the backend URL, for example:

`https://voicelab-api.onrender.com`

Test:

`https://voicelab-api.onrender.com/api/health`

## 3. Deploy the frontend on Netlify

Import the same GitHub repository into Netlify. `netlify.toml` already sets:

- Build command: `node scripts/netlify-config.mjs`
- Publish directory: `apps/web`

In **Project configuration → Environment variables**, add:

`VOICELAB_API_BASE=https://YOUR-RENDER-SERVICE.onrender.com`

Then deploy. Netlify will generate `apps/web/config.js` at build time and the browser will send API/audio requests directly to Render.

## 4. Allow the Netlify origin in Render

After Netlify gives you the production URL, set Render's `CORS_ORIGINS` to the exact site origin, for example:

`https://your-voicelab.netlify.app`

For local + production development you can use a comma-separated value:

`http://localhost:8000,http://localhost:8888,https://your-voicelab.netlify.app`

Redeploy/restart the Render service after changing it.

## 5. Optional custom domain

A clean production layout is:

- `https://voice.example.com` → Netlify frontend
- `https://api.voice.example.com` → Render backend

If you add the frontend custom domain, add that exact origin to `CORS_ORIGINS` too.

## Important production notes

- Never place provider API keys in `apps/web`, `config.js`, or Netlify frontend variables other than `VOICELAB_API_BASE`.
- The Render disk is important because the current build uses SQLite and local output files.
- If you switch generated media to S3/R2 using VoiceLab's Admin storage settings, keep the persistent disk anyway unless the SQLite database is also migrated to a managed database.
- Demucs is CPU/RAM intensive. Choose backend compute accordingly.
