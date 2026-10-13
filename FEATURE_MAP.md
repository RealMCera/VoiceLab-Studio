# VoiceLab Studio — Feature Map

## Core studio
- AI text-to-speech with searchable voice cards
- Speed, volume, emotion, and intensity controls
- Character / licensed / studio voice views
- Upload or microphone recording for voice-to-voice conversion
- AI sound-effect generation
- AI Cover pipeline with stem separation, conversion, and remix
- Vocal isolator
- Vocal remover
- Video/audio extractor

## Product polish added in v0.2
- Real server-side **generation queue** backed by SQLite
- Persistent job status, percentage, phase, output, and error state
- Queue page that keeps updating while long jobs run
- Browser waveform rendering for generated audio and history items
- Persistent **Favorites** for marketplace entries and usable voices
- Expanded Marketplace filters: provider, type, access, capability, favorites, sorting
- Marketplace summary metrics
- Persistent generation / processing history with playback and download
- Voice Library browser with favorites-first sorting
- Provider Setup screen with local connect / replace / disconnect controls
- API keys written to `apps/api/.env` server-side and never returned to the browser
- Diagnostics for FFmpeg, Demucs, and configured providers

## Voice Marketplace
- 88 researched entries bundled in `apps/api/voice_catalog.json`
- ElevenLabs Iconic Marketplace
- ElevenLabs shared Voice Library
- Respeecher
- Speechify
- Voice-Swap
- Kits AI
- Veritone Voice

### Live provider sync
- ElevenLabs shared Professional Voice Clones
- Respeecher licensed TTS voices
- Speechify shared voices
- Kits voice models

## Provider adapters
- OpenAI — TTS
- ElevenLabs — TTS, shared voice import, SFX, voice conversion
- Respeecher — discovery + TTS
- Speechify — discovery + TTS
- Kits AI — voice model discovery + conversion
- Demucs — local two-stem separation
- FFmpeg — extraction, mastering, and remix

## Safety / rights model
- Manual provider voices require explicit authorization confirmation
- Public-figure/iconic marketplace entries preserve their provider access status
- Approval-required voices are not presented as instantly available
- Generated speech is labeled as AI-generated in the UI

## Product Suite v0.3

| Feature | Status | Implementation |
|---|---|---|
| Accounts / profiles | Working | SQLite users + PBKDF2 password hashes + bearer sessions |
| First-user administrator | Working | First registered account receives admin role |
| Public clip sharing | Working | Random share token + standalone playback/download page |
| A/B voice comparison | Working | Two simultaneous queued TTS generations |
| Waveform audio editor | Working | Browser waveform + FFmpeg trim/gain/fade export |
| Cover key/pitch | Working | Local -12 to +12 semitone transposition after voice conversion |
| Cover mix levels | Working | Independent vocal/instrumental dB controls |
| Admin catalog controls | Working | Enable/disable marketplace catalog entries |
| Admin workspace metrics | Working | Users, jobs, outputs, shares, custom voices |
| Local storage | Working | Default output storage |
| S3-compatible cloud mirror | Working when configured | boto3 adapter + optional custom endpoint/public base URL |
| History → Edit | Working | Opens selected output directly in editor |
| History → Share | Working | Creates/copies public share URL |
| History → Cloud | Working when signed in/configured | Uploads selected local output to configured S3-compatible storage |
