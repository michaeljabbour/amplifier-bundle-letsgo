---
skill:
  name: voice-config
  version: 1.0.0
  description: Guide for configuring voice transcription and TTS providers
  tags:
    - voice
    - configuration
    - setup
---

# Voice Configuration Guide

## Gateway Voice Middleware

Add a `voice` section to `~/.letsgo/gateway/config.yaml`:

```yaml
voice:
  enabled: true
  transcription:
    provider: "whisper-api"    # Options: "whisper-api", "local-whisper"
    api_key: "<stored-in-secrets>"
    model: "whisper-1"
  tts:
    enabled: false              # TTS is opt-in
    provider: "edge-tts"        # Options: "edge-tts", "elevenlabs", "openai-tts"
    voice: "en-US-AriaNeural"   # Provider-specific voice name
```

## Provider Setup

### Transcription: OpenAI Whisper API (Recommended)
1. Get API key from https://platform.openai.com/api-keys
2. Store: `secrets set_secret voice/whisper/api_key <key> api_key`
3. Set `transcription.provider: "whisper-api"` in config

### Transcription: Local Whisper (Free, requires GPU)
1. Install: `pip install openai-whisper`
2. Set `transcription.provider: "local-whisper"` in config
3. Model options: tiny, base, small, medium, large

### TTS: edge-tts (Free, No API Key)
1. Install: `pip install edge-tts`
2. Set `tts.provider: "edge-tts"` in config
3. Voices: en-US-AriaNeural, en-US-GuyNeural, en-GB-SoniaNeural, etc.

### TTS: ElevenLabs (High Quality)
1. Get API key from https://elevenlabs.io
2. Store: `secrets set_secret voice/elevenlabs/api_key <key> api_key`
3. Set `tts.provider: "elevenlabs"` in config

### TTS: OpenAI TTS
1. Uses same API key as Whisper (if using OpenAI for both)
2. Set `tts.provider: "openai-tts"` in config
3. Voices: alloy, echo, fable, onyx, nova, shimmer