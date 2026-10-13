# Voice catalog research export

Catalog entries: **88**

## Provider counts

- **ElevenLabs:** 1
- **ElevenLabs Iconic:** 39
- **Kits AI:** 6
- **Respeecher:** 8
- **Speechify:** 9
- **Veritone Voice:** 10
- **Voice-Swap:** 15

## Access counts

- **enterprise:** 1
- **provider_account:** 38
- **request_license:** 49

## Provider notes

### ElevenLabs
Iconic Marketplace entries remain approval-required. Shared Professional Voice Clones can be synced through your ElevenLabs account and imported into VoiceLab Studio.

### Respeecher
The build supports live licensed TTS voice discovery and TTS generation through a configured Respeecher API key. Celebrity/project voices may have separate moderation or licensing requirements.

### Speechify
The build supports live shared-voice discovery and TTS. Celebrity names in the static research catalog reflect voices advertised by Speechify; availability and usage rights remain provider/account dependent.

### Kits AI
The build supports live voice-model discovery plus asynchronous voice conversion. Imported Kits models are marked conversion-only because the current app does not rely on Kits for TTS.

### Voice-Swap
Catalog entries cover rights-managed singing/voiceover talent publicly presented by Voice-Swap. Public API access exists, but no undocumented/private endpoint is guessed in this build.

### Veritone Voice
Premium/stock voice offerings are catalogued. Direct adapter work is deferred until API/account details are available for the target account.

## Machine-readable source
`apps/api/voice_catalog.json` is the file loaded by the Marketplace API.
