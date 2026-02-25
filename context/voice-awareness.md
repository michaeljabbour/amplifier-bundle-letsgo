# Voice Capabilities

You have access to voice processing capabilities through the LetsGo gateway.

## Automatic Voice Transcription

When users send voice messages through any channel (Telegram, WhatsApp, Discord, etc.), their audio is automatically transcribed to text before reaching you. You'll see transcriptions formatted as:

```
[Voice message transcription: "the transcribed text"]
```

Treat these transcriptions as the user's actual message. Respond naturally in text — the gateway may optionally convert your response to audio.

## Explicit Media Pipeline Tool

You can also use the `media_pipeline` tool explicitly for on-demand audio processing:

- **Transcribe**: Convert any audio file to text
  - Action: `transcribe`, provide `audio_path`
- **Synthesize**: Convert text to audio
  - Action: `synthesize`, provide `text` and `output_path`

Use explicit transcription for tasks like "transcribe this podcast" or "what does this audio say". Use explicit synthesis for "read this aloud" or "create an audio version".

## Voice Providers

Transcription providers: OpenAI Whisper API, local Whisper CLI
TTS providers: edge-tts (free), ElevenLabs, OpenAI TTS