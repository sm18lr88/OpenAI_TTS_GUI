from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

from .config import settings
from .errors import ConfigError, TTSError
from .keystore import read_api_key
from .tts import TTSService


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
        choices=settings.TTS_MODELS,
        help=f"TTS model. Choices: {_choices_text(settings.TTS_MODELS)}",
    )
    tts_group.add_argument(
        "--voice",
        default="alloy",
        choices=settings.TTS_VOICES,
        help=f"Voice. Choices: {_choices_text(settings.TTS_VOICES)}",
    )
    tts_group.add_argument(
        "--format",
        default="mp3",
        choices=settings.TTS_FORMATS,
        help=f"Output audio format. Choices: {_choices_text(settings.TTS_FORMATS)}",
    )
    tts_group.add_argument(
        "--speed",
        type=float,
        default=settings.DEFAULT_SPEED,
        help=f"Playback speed from {settings.MIN_SPEED} to {settings.MAX_SPEED}",
    )
    tts_group.add_argument(
        "--instructions",
        default="",
        help=f"Optional voice/tone guidance for {settings.GPT_4O_MINI_TTS_MODEL}",
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
    print(f"{settings.APP_NAME} {settings.APP_VERSION}")


def main(argv: list[str] | None = None) -> int:
    settings.ensure_directories()
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

    if not math.isfinite(args.speed) or not (
        settings.MIN_SPEED <= args.speed <= settings.MAX_SPEED
    ):
        print(
            f"Invalid speed: must be between {settings.MIN_SPEED} and {settings.MAX_SPEED}.",
            file=sys.stderr,
        )
        return 2

    api_key = read_api_key()
    if not api_key:
        print("Missing OPENAI API key.", file=sys.stderr)
        return 1

    try:
        text = Path(args.infile).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"Failed to read input file: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(level=getattr(logging, args.log_level), force=True)

    try:
        service = TTSService(
            api_key=api_key,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.OPENAI_TIMEOUT,
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


if __name__ == "__main__":
    raise SystemExit(main())
