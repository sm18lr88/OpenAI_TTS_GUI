# OpenAI TTS – Minimal Spec

## Inputs
- Text: UTF-8 string (arbitrary length; split into chunks of `MAX_CHUNK_SIZE`).
- Model: one of `config.TTS_MODELS`.
- Voice: one of `config.TTS_VOICES`.
- Format: one of `config.TTS_FORMATS`.
- Speed: float in [`MIN_SPEED`, `MAX_SPEED`].
- Instructions: optional (applies only to `config.GPT_4O_MINI_TTS_MODEL`).
- API key: env `OPENAI_API_KEY`, keyring, or `api_key.enc`.

## Behavior
1. Preflight: verify `ffmpeg` present and >= `FFMPEG_MIN_VERSION`.
2. Split text into chunks honoring sentence boundaries when possible.
3. For each chunk: call OpenAI audio.speech with streaming-to-file; exponential backoff with jitter; honor `Retry-After` when present.
4. Concatenate chunks with `ffmpeg -f concat`, forcing consistent output params:
   - sample rate `OUTPUT_SAMPLE_RATE`, channels `OUTPUT_CHANNELS`, bitrate `OUTPUT_BITRATE` (where applicable).
5. On success: write sidecar JSON `<output>.json` with environment snapshot, parameters, and request IDs.

## Outputs
- Audio file at requested `output_path`.
- Sidecar `<output_path>.json`.
- Logs at `tts_app.log`.

## Limits / Assumptions
- Chunking by characters (not tokens); API-specific token limits are not enforced.
- Instructions are only used for `gpt-4o-mini-tts`.
- Keyring preferred; file fallback is XOR-obfuscated (not encryption).

## Failure Modes
- Missing/old ffmpeg → fatal with message.
- OpenAI errors: retries for 5xx/timeout/connection; user-visible error on other failures.
- I/O errors during concat or write → fatal with message.

## Env / Versions
- Snapshot fields: app name/version, Python, platform, `openai`, `PyQt6`, ffmpeg first line.

## CLI
`openai-tts --in text.txt --out out.mp3 --model tts-1 --voice alloy --format mp3 --speed 1.0`
