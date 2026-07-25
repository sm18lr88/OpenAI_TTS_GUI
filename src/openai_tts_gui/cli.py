from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from . import config
from .errors import ConfigError, TTSError
from .keystore import credential_value, read_api_key_outcome, stale_legacy_credential_guidance

if TYPE_CHECKING:
    from .tts import TTSService

settings = config
logger = logging.getLogger(__name__)


def _choices_text(values: list[str]) -> str:
    return ", ".join(values)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openai-tts",
        description="Generate speech audio from text via OpenAI TTS API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    input_group = parser.add_argument_group("Input/output")
    input_group.add_argument("--in", dest="infile", help="Input UTF-8 text file")
    input_group.add_argument("--out", dest="outfile", help="Output audio path")

    tts_group = parser.add_argument_group("TTS options")
    tts_group.add_argument(
        "--model",
        default="tts-1",
        choices=config.TTS_MODELS,
        help=f"TTS model. Choices: {_choices_text(config.TTS_MODELS)}",
    )
    tts_group.add_argument(
        "--voice",
        default="alloy",
        choices=config.TTS_VOICES,
        help=f"Voice. Choices: {_choices_text(config.TTS_VOICES)}",
    )
    tts_group.add_argument(
        "--format",
        default="mp3",
        choices=config.TTS_FORMATS,
        help=f"Output audio format. Choices: {_choices_text(config.TTS_FORMATS)}",
    )
    tts_group.add_argument(
        "--speed",
        type=float,
        default=config.DEFAULT_SPEED,
        help=f"Playback speed from {config.MIN_SPEED} to {config.MAX_SPEED}",
    )
    tts_group.add_argument(
        "--instructions",
        default="",
        help=f"Optional voice/tone guidance for {config.GPT_4O_MINI_TTS_MODEL}",
    )
    tts_group.add_argument(
        "--retain-files",
        action="store_true",
        help="Keep intermediate chunk files next to the output",
    )

    runtime_group = parser.add_argument_group("Runtime options")
    runtime_group.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    runtime_group.add_argument("--version", action="store_true", help="Print version and exit")
    return parser


def _print_version() -> None:
    print(f"{config.APP_NAME} {config.APP_VERSION}")


def _load_tts_service() -> type[TTSService]:
    from .tts import TTSService

    return TTSService


def main(argv: list[str] | None = None) -> int:
    config.ensure_directories()
    args_list = list(sys.argv[1:] if argv is None else argv)

    if "--version" in args_list:
        _print_version()
        return 0

    parser = _build_parser()
    args = parser.parse_args(args_list)

    if args.version:
        _print_version()
        return 0

    if not args.infile or not args.outfile:
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: the following arguments are required: --in, --out",
            file=sys.stderr,
        )
        return 2

    if not math.isfinite(args.speed) or not (config.MIN_SPEED <= args.speed <= config.MAX_SPEED):
        print(
            f"Invalid speed: must be between {config.MIN_SPEED} and {config.MAX_SPEED}.",
            file=sys.stderr,
        )
        return 2

    handler = config.configure_cli_logging(getattr(logging, args.log_level))
    try:
        credential = read_api_key_outcome()
        api_key = credential_value(credential)
        guidance = stale_legacy_credential_guidance(credential)
        if guidance is not None:
            logger.warning(
                guidance,
                extra={
                    "event": "credential.legacy_cleanup_required",
                    "outcome": "stale_legacy_credential",
                },
            )
        if not api_key:
            print("Missing OPENAI API key.", file=sys.stderr)
            return 1
        try:
            text = Path(args.infile).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"Failed to read input file: {exc}", file=sys.stderr)
            return 1
        try:
            service = _load_tts_service()(
                api_key=api_key,
                base_url=config.OPENAI_BASE_URL,
                timeout=config.OPENAI_TIMEOUT,
            )
            service.generate(
                text=text,
                output_path=str(args.outfile),
                model=args.model,
                voice=args.voice,
                response_format=args.format,
                speed=float(args.speed),
                instructions=args.instructions,
                retain_files=bool(args.retain_files),
            )
        except ConfigError as exc:
            print(f"Invalid configuration: {exc}", file=sys.stderr)
            return 2
        except TTSError as exc:
            print(f"TTS failed: {exc}", file=sys.stderr)
            return 1
        return 0
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
