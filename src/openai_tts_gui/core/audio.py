from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..config import settings
from ..errors import FFmpegError, FFmpegNotFoundError, TTSChunkError

logger = logging.getLogger(__name__)


def _normalize_paths(file_list: Sequence[str]) -> list[Path]:
    paths = [Path(path) for path in file_list]
    if not paths:
        raise TTSChunkError("No audio files were provided for concatenation.")
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise TTSChunkError(
            "Missing audio file(s) for concatenation: " + ", ".join(sorted(missing))
        )
    return paths


def _ffmpeg_concat_entry(path: Path) -> str:
    normalized = path.resolve().as_posix().replace("'", r"\'")
    return f"file '{normalized}'\n"


def concatenate_audio_files(file_list: Sequence[str], output_file: str) -> str:
    input_paths = _normalize_paths(file_list)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Attempting to concatenate %d file(s) into %s",
        len(input_paths),
        output_path,
    )

    if len(input_paths) == 1:
        source_path = input_paths[0]
        if source_path.resolve() == output_path.resolve():
            logger.info("Single input file is already at the destination: %s", output_path)
            return str(output_path)
        if output_path.exists():
            output_path.unlink()
        try:
            shutil.move(str(source_path), str(output_path))
        except OSError as exc:
            logger.exception("Failed to move %s to %s", source_path, output_path)
            raise TTSChunkError(
                f"Failed to move generated audio into place: {exc}",
                file_path=str(output_path),
            ) from exc
        logger.info("Moved single audio file %s to %s", source_path, output_path)
        return str(output_path)

    ext = output_path.suffix.lower().lstrip(".")
    codec = settings.CODEC_MAP.get(ext, settings.DEFAULT_CODEC)
    params = settings.CODEC_PARAMS.get(ext, {})

    concat_list_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="concat_",
            suffix=".txt",
            dir=output_path.parent,
            delete=False,
        ) as handle:
            concat_list_path = Path(handle.name)
            for file_path in input_paths:
                handle.write(_ffmpeg_concat_entry(file_path))

        concat_command = [
            settings.FFMPEG_COMMAND,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c:a",
            codec,
        ]
        if params.get("ar"):
            concat_command += ["-ar", str(params["ar"])]
        if params.get("ac"):
            concat_command += ["-ac", str(params["ac"])]
        if params.get("b:a"):
            concat_command += ["-b:a", str(params["b:a"])]
        concat_command.append(str(output_path))

        logger.info("Executing ffmpeg for concatenation into %s", output_path)
        result = subprocess.run(
            concat_command,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.debug("ffmpeg stdout: %s", result.stdout)
        logger.debug("ffmpeg stderr: %s", result.stderr)
        logger.info("Successfully concatenated files to %s", output_path)
        return str(output_path)
    except FileNotFoundError as exc:
        logger.error(
            "%s command not found. Ensure ffmpeg is installed and on PATH.",
            settings.FFMPEG_COMMAND,
        )
        raise FFmpegNotFoundError(
            f"{settings.FFMPEG_COMMAND} not found. Ensure ffmpeg is installed and on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        logger.error("ffmpeg concatenation failed with exit code %s", exc.returncode)
        if stderr:
            logger.error("ffmpeg stderr: %s", stderr)
        raise FFmpegError(
            f"ffmpeg concatenation failed with exit code {exc.returncode}: {stderr or exc}"
        ) from exc
    except OSError as exc:
        logger.exception("File I/O error during concatenation")
        raise TTSChunkError(
            f"File I/O error during concatenation: {exc}",
            file_path=str(output_path),
        ) from exc
    finally:
        if concat_list_path is not None and concat_list_path.exists():
            try:
                concat_list_path.unlink()
            except OSError:
                logger.warning("Failed to remove temporary concat list %s", concat_list_path)


def cleanup_files(file_list: Iterable[str]) -> None:
    files = [Path(path) for path in file_list]
    logger.info("Cleaning up %d temporary file(s).", len(files))
    for file_path in files:
        if not file_path.exists():
            logger.debug("Temporary file already absent: %s", file_path)
            continue
        try:
            file_path.unlink()
            logger.debug("Deleted temporary file: %s", file_path)
        except OSError as exc:
            logger.warning("Failed to delete temporary file %s: %s", file_path, exc)
