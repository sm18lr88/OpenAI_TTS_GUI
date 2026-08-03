from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .. import config
from ..errors import CleanupReport, FFmpegError, TTSCancelledError, TTSChunkError
from ._ffmpeg_process import FfmpegProcess
from .ffmpeg import resolve_ffmpeg_command

logger = logging.getLogger(__name__)
settings = config
_ffmpeg_process_owner: ContextVar[Callable[[FfmpegProcess], bool] | None] = ContextVar(
    "ffmpeg_process_owner", default=None
)


@contextmanager
def own_ffmpeg_process(owner: Callable[[FfmpegProcess], bool]) -> Iterator[None]:
    token = _ffmpeg_process_owner.set(owner)
    try:
        yield
    finally:
        _ffmpeg_process_owner.reset(token)


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
        "Combining %d file(s) into %s",
        len(input_paths),
        output_path,
    )

    if len(input_paths) == 1:
        source_path = input_paths[0]
        if source_path.resolve() == output_path.resolve():
            logger.info("The single input file is already at the destination: %s", output_path)
            return str(output_path)
        try:
            os.replace(source_path, output_path)
        except OSError as exc:
            logger.exception("Could not move %s to %s", source_path, output_path)
            raise TTSChunkError(
                f"Could not move the generated audio to the output path: {exc}",
                file_path=str(output_path),
            ) from exc
        logger.info("Replaced single audio file %s at %s", source_path, output_path)
        return str(output_path)

    ext = output_path.suffix.lower().lstrip(".")
    codec = config.CODEC_MAP.get(ext, config.DEFAULT_CODEC)
    params = config.CODEC_PARAMS.get(ext, {})

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

        ffmpeg_command = resolve_ffmpeg_command()
        concat_command = [
            ffmpeg_command,
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

        logger.info("Running ffmpeg to combine files into %s", output_path)
        result = FfmpegProcess(concat_command).run(_ffmpeg_process_owner.get())
        logger.debug("ffmpeg stdout: %s", result.stdout)
        logger.debug("ffmpeg stderr: %s", result.stderr)
        if result.cancelled_before_attach or result.stop_requested:
            raise TTSCancelledError("TTS generation cancelled.")
        if result.returncode != 0:
            raise FFmpegError(
                "ffmpeg concatenation failed with exit code "
                f"{result.returncode}: {result.stderr.strip()}"
            )
        logger.info("Combined files into %s", output_path)
        return str(output_path)
    except OSError as exc:
        logger.exception("File I/O error while combining audio")
        raise TTSChunkError(
            f"File I/O error while combining audio: {exc}",
            file_path=str(output_path),
        ) from exc
    finally:
        if concat_list_path is not None and concat_list_path.exists():
            try:
                concat_list_path.unlink()
            except OSError:
                logger.warning("Could not remove the temporary concat list %s", concat_list_path)


def cleanup_files(file_list: Iterable[str]) -> CleanupReport:
    files = [Path(path) for path in file_list]
    logger.info("Removing %d temporary file(s).", len(files))
    retained: list[str] = []
    warnings: list[str] = []
    for file_path in files:
        if not file_path.exists():
            logger.debug("Temporary file already absent: %s", file_path)
            continue
        try:
            file_path.unlink()
            logger.debug("Deleted temporary file: %s", file_path)
        except OSError as exc:
            logger.warning("Could not delete temporary file %s: %s", file_path, exc)
            retained.append(file_path.name)
            warnings.append(f"could not remove temporary file {file_path.name}: {exc}")
    return CleanupReport(tuple(sorted(set(retained))), tuple(sorted(set(warnings))))
