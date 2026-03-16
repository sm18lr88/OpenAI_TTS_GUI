import logging
import os
import subprocess

from ..config import settings

logger = logging.getLogger(__name__)


def concatenate_audio_files(file_list: list[str], output_file: str):
    logger.info(f"Attempting to concatenate {len(file_list)} files into {output_file}")
    if not file_list:
        logger.warning("No files provided for concatenation.")
        return

    if len(file_list) == 1:
        try:
            if os.path.exists(file_list[0]):
                output_dir = os.path.dirname(output_file)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                if os.path.exists(output_file):
                    os.remove(output_file)
                os.rename(file_list[0], output_file)
                logger.info(f"Renamed single file '{file_list[0]}' to '{output_file}'")
            else:
                logger.error(f"Single input file not found: {file_list[0]}")
                raise FileNotFoundError(f"Input file missing: {file_list[0]}")
            return
        except OSError as e:
            logger.exception(
                f"Failed to rename single file '{file_list[0]}' to '{output_file}': {e}"
            )
            raise

    output_dir = os.path.dirname(output_file) or "."
    concat_list_path = os.path.join(output_dir, "concat_list.txt")

    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(concat_list_path, "w", encoding="utf-8") as f:
            for file_path in file_list:
                if os.path.exists(file_path):
                    abs_path = os.path.abspath(file_path).replace("\\", "/")
                    f.write(f"file '{abs_path}'\n")
                else:
                    logger.error(f"File listed for concatenation not found: {file_path}. Skipping.")

        ext = os.path.splitext(output_file)[1].lower().lstrip(".")
        codec = settings.CODEC_MAP.get(ext, settings.DEFAULT_CODEC)
        params = settings.CODEC_PARAMS.get(ext, {})

        concat_command = [
            settings.FFMPEG_COMMAND,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c:a",
            codec,
        ]
        if params.get("ar"):
            concat_command += ["-ar", str(params["ar"])]
        if params.get("ac"):
            concat_command += ["-ac", str(params["ac"])]
        if params.get("b:a"):
            concat_command += ["-b:a", str(params["b:a"])]
        concat_command.append(output_file)
        logger.info(f"Executing ffmpeg: {' '.join(concat_command)}")

        result = subprocess.run(
            concat_command,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.debug(f"ffmpeg stdout: {result.stdout}")
        logger.debug(f"ffmpeg stderr: {result.stderr}")
        logger.info(f"Successfully concatenated files to {output_file}")

    except FileNotFoundError:
        logger.error(
            "'%s' command not found. Ensure ffmpeg is installed and in your system's PATH.",
            settings.FFMPEG_COMMAND,
        )
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg concatenation failed with exit code {e.returncode}.")
        logger.error(f"ffmpeg stderr: {e.stderr}")
        raise
    except OSError as e:
        logger.exception(f"File I/O error during concatenation setup: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during audio concatenation: {e}")
        raise
    finally:
        if os.path.exists(concat_list_path):
            try:
                os.remove(concat_list_path)
            except OSError as e:
                logger.error(f"Failed to remove temporary concat list {concat_list_path}: {e}")


def cleanup_files(file_list: list[str]):
    logger.info(f"Cleaning up {len(file_list)} temporary files.")
    for file_path in file_list:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Deleted temporary file: {file_path}")
            except OSError as e:
                logger.error(f"Failed to delete temporary file {file_path}: {e}")
        else:
            logger.warning(f"Temporary file not found for deletion: {file_path}")
