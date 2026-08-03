# OpenAI TTS Minimal Spec

## Inputs
- Text: UTF-8 string of arbitrary length. Split it into chunks of `MAX_CHUNK_SIZE`.
- Model: one of `config.TTS_MODELS`.
- Voice: one of `config.TTS_VOICES` (alloy, ash, ballad, cedar, coral, echo, fable, marin, onyx, nova, sage, shimmer, verse).
- Format: one of `config.TTS_FORMATS`.
- Speed: float in [`MIN_SPEED`, `MAX_SPEED`].
- Instructions: optional (applies only to `config.GPT_4O_MINI_TTS_MODEL`).
- API key: env `OPENAI_API_KEY`, keyring, or `api_key.enc`.

## Behavior
1. Before generation, verify that `ffmpeg` is present and >= `FFMPEG_MIN_VERSION`.
2. Split text into chunks. Honor sentence boundaries when possible.
3. For each chunk, call OpenAI audio.speech with `stream_format="audio"`. Stream the response to a file. Use exponential backoff with jitter. Honor `Retry-After` when present.
4. Concatenate chunks with `ffmpeg -f concat`. Force consistent output parameters:
   - sample rate `OUTPUT_SAMPLE_RATE`, channels `OUTPUT_CHANNELS`, bitrate `OUTPUT_BITRATE` (where applicable).
5. On success, write sidecar JSON `<output>.json` with the environment snapshot, parameters, and request IDs.

## Outputs
- Audio file at requested `output_path`.
- Sidecar `<output_path>.json`.
- Logs at `tts_app.log`.

## Limits / Assumptions
- The app chunks by characters, not tokens. It does not enforce API-specific token limits.
- Instructions are only used for `gpt-4o-mini-tts`.
- The keyring is preferred. The file fallback is XOR-obfuscated, not encrypted.

## Failure Modes
- Missing or old ffmpeg: Fatal error with a message.
- OpenAI errors: Retry for 5xx, timeout, or connection errors. Show the user an error for other failures.
- I/O errors during concat or write: Fatal error with a message.

## Env / Versions
- Snapshot fields: app name/version, Python, platform, `openai`, `PyQt6`, and the first ffmpeg line.
- The OpenAI Python SDK is v2.9.0. PyQt6 is v6.10.0.

## CLI
`openai-tts --in text.txt --out out.mp3 --model tts-1 --voice alloy --format mp3 --speed 1.0`
