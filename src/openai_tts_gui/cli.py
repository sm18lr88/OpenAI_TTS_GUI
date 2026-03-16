import argparse
import logging
import sys

from . import config
from .config import settings
from .errors import TTSError
from .keystore import read_api_key
from .tts import TTSService


def main(argv=None):
    config.ensure_directories()
    if argv is None:
        argv = sys.argv[1:]
    if "--version" in argv:
        print(f"{settings.APP_NAME} {settings.APP_VERSION}")
        return 0

    parser = argparse.ArgumentParser(
        prog="openai-tts",
        description="Generate speech audio from text via OpenAI TTS API.",
    )
    parser.add_argument("--in", dest="infile", help="Input text file")
    parser.add_argument("--out", dest="outfile", help="Output audio path")
    parser.add_argument("--model", default="tts-1", choices=settings.TTS_MODELS)
    parser.add_argument("--voice", default="alloy", choices=settings.TTS_VOICES)
    parser.add_argument("--format", default="mp3", choices=settings.TTS_FORMATS)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--instructions", default="")
    parser.add_argument("--retain-files", action="store_true")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args(argv)

    if args.version:
        print(f"{settings.APP_NAME} {settings.APP_VERSION}")
        return 0
    if not args.infile or not args.outfile:
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: the following arguments are required: --in, --out",
            file=sys.stderr,
        )
        return 2

    api_key = read_api_key()
    if not api_key:
        print("Missing OPENAI API key.", file=sys.stderr)
        return 1

    with open(args.infile, encoding="utf-8") as f:
        text = f.read()

    logging.basicConfig(level=getattr(logging, args.log_level))

    try:
        service = TTSService(
            api_key=api_key,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.OPENAI_TIMEOUT,
        )
        service.generate(
            text=text,
            output_path=args.outfile,
            model=args.model,
            voice=args.voice,
            response_format=args.format,
            speed=float(args.speed),
            instructions=args.instructions,
            retain_files=bool(args.retain_files),
        )
    except TTSError as e:
        print(f"TTS failed: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
