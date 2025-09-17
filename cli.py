import argparse
import sys

import config
import utils
from tts import TTSProcessor


def main(argv=None):
    # Be robust: allow --version without requiring --in/--out
    if argv is None:
        argv = sys.argv[1:]
    if "--version" in argv:
        print(f"{config.APP_NAME} {config.APP_VERSION}")
        return 0

    parser = argparse.ArgumentParser(description="OpenAI TTS CLI")
    # Allow --version to run standalone; validate required args only when not --version
    parser.add_argument("--in", dest="infile", help="Input text file")
    parser.add_argument("--out", dest="outfile", help="Output audio path")
    parser.add_argument("--model", default="tts-1")
    parser.add_argument("--voice", default="alloy")
    parser.add_argument("--format", default="mp3", choices=config.TTS_FORMATS)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--instructions", default="")
    parser.add_argument("--retain-files", action="store_true")
    # --version is handled early above; keep the flag so argparse doesn't error on unknown
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args(argv)

    # If someone passed --version alongside required args, honor early return too
    if args.version:
        print(f"{config.APP_NAME} {config.APP_VERSION}")
        return 0
    # Enforce required args only when not --version
    if not args.infile or not args.outfile:
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: the following arguments are required: --in, --out",
            file=sys.stderr,
        )
        return 2

    api_key = utils.read_api_key()
    if not api_key:
        print("Missing OPENAI API key.", file=sys.stderr)
        return 1

    with open(args.infile, encoding="utf-8") as f:
        text = f.read()

    params = {
        "api_key": api_key,
        "text": text,
        "output_path": args.outfile,
        "model": args.model,
        "voice": args.voice,
        "response_format": args.format,
        "speed": float(args.speed),
        "instructions": args.instructions,
        "retain_files": bool(args.retain_files),
    }

    # Run synchronously via thread.run()
    tp = TTSProcessor(params)
    tp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
