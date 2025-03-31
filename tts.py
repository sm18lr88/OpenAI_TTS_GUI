import os
import time
import logging
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal
from openai import OpenAI, RateLimitError, APIError, OpenAIError

import config  # Import configuration
from utils import split_text, concatenate_audio_files, cleanup_files

# Setup logger for this module
logger = logging.getLogger(__name__)


class TTSProcessor(QThread):
    """
    Handles the TTS generation process in a separate thread.
    Emits signals for progress updates, completion, or errors.
    """

    progress_updated = pyqtSignal(int)  # Percentage (0-100)
    tts_complete = pyqtSignal(str)  # Success message
    tts_error = pyqtSignal(str)  # Error message

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self.params = params
        self.temp_files = []
        self.client = None  # Initialize OpenAI client later

    def run(self):
        """The main execution method for the thread."""
        logger.info("TTSProcessor thread started.")
        try:
            self.client = OpenAI(
                api_key=self.params["api_key"]
            )  # Initialize client here

            text = self.params["text"]
            output_path = self.params["output_path"]
            model = self.params["model"]
            voice = self.params["voice"]
            response_format = self.params["response_format"]
            speed = self.params["speed"]
            instructions = self.params["instructions"]
            retain_files = self.params["retain_files"]

            # Split text into manageable chunks
            chunks = split_text(text, config.MAX_CHUNK_SIZE)
            total_chunks = len(chunks)
            if total_chunks == 0:
                raise ValueError("No text chunks generated after splitting.")

            logger.info(f"Processing {total_chunks} text chunks.")
            self.progress_updated.emit(1)  # Indicate start

            output_dir = os.path.dirname(output_path)
            base_filename = os.path.splitext(os.path.basename(output_path))[0]

            # Process each chunk
            for i, chunk in enumerate(chunks):
                chunk_start_time = time.time()
                logger.info(f"Processing chunk {i+1}/{total_chunks}...")

                temp_filename = os.path.join(
                    output_dir, f"{base_filename}_chunk_{i+1}.{response_format}"
                )
                self.temp_files.append(temp_filename)

                success = self._save_chunk_with_retries(
                    chunk,
                    temp_filename,
                    model,
                    voice,
                    response_format,
                    speed,
                    instructions,
                )

                if not success:
                    # Error message handled within _save_chunk_with_retries
                    # No need to emit another error here, just stop.
                    return  # Exit the run method

                chunk_duration = time.time() - chunk_start_time
                logger.info(f"Chunk {i+1} processed in {chunk_duration:.2f} seconds.")

                # Update progress (avoid reaching 100% until concatenation)
                progress = int(
                    ((i + 1) / total_chunks) * 95
                )  # Cap at 95% before concat
                self.progress_updated.emit(progress)

            # Concatenate audio files
            logger.info("Concatenating audio chunks...")
            concatenate_audio_files(self.temp_files, output_path)
            self.progress_updated.emit(100)  # Signal completion
            logger.info(f"TTS generation complete. Output saved to: {output_path}")
            self.tts_complete.emit(f"TTS audio saved successfully to:\n{output_path}")

        except (
            ValueError,
            FileNotFoundError,
            subprocess.CalledProcessError,
            IOError,
        ) as e:  # <--- Error was caught here
            logger.exception(f"Error during TTS processing setup or concatenation: {e}")
            self.tts_error.emit(f"Processing failed: {e}")
        except OpenAIError as e:
            # This catches API related errors not handled by retry loop (e.g., auth, config)
            logger.exception(f"OpenAI API error during processing: {e}")
            self.tts_error.emit(f"OpenAI API Error: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred in TTSProcessor: {e}")
            self.tts_error.emit(f"An unexpected error occurred: {e}")
        finally:
            # Cleanup temporary files if needed, regardless of success/error
            if not self.params.get("retain_files", False):
                cleanup_files(self.temp_files)
            logger.info("TTSProcessor thread finished.")

    def _save_chunk_with_retries(
        self,
        text_chunk: str,
        filename: str,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        instructions: str | None,
    ) -> bool:
        """Attempts to generate and save a single TTS chunk with retries."""
        logger.info(f"Attempting to generate audio for chunk, saving to {filename}")

        # Prepare API call parameters
        api_params = {
            "model": model,
            "voice": voice,
            "input": text_chunk,
            "response_format": response_format,
            "speed": speed,
        }
        # Only include instructions if the model supports it and they are provided
        if model == config.GPT_4O_MINI_TTS_MODEL and instructions:
            api_params["instructions"] = instructions

        for attempt in range(config.MAX_RETRIES):
            try:
                logger.debug(
                    f"API call attempt {attempt + 1}/{config.MAX_RETRIES} for {os.path.basename(filename)}"
                )
                start_time = time.time()

                response = self.client.audio.speech.create(**api_params)

                api_call_duration = time.time() - start_time
                logger.debug(f"API call successful in {api_call_duration:.2f} seconds.")

                # Write the audio content to the file
                with open(filename, "wb") as file:
                    # response.stream_to_file(filename) # Efficient way if available/needed
                    file.write(response.content)

                logger.info(f"Successfully saved chunk to {filename}")
                return True

            except RateLimitError as e:
                wait_time = config.RETRY_DELAY * (attempt + 1)  # Simple linear backoff
                logger.warning(
                    f"Rate limit hit on attempt {attempt + 1}. Retrying in {wait_time} seconds... Error: {e}"
                )
                time.sleep(wait_time)  # Wait before retrying

            except APIError as e:
                # Catch other specific API errors (e.g., server error, bad request)
                logger.error(
                    f"OpenAI API error on attempt {attempt + 1}: {e.status_code} - {e.message}"
                )
                # Decide if retryable. 5xx errors might be, 4xx usually not.
                if e.status_code >= 500 and attempt < config.MAX_RETRIES - 1:
                    wait_time = config.RETRY_DELAY * (attempt + 1)
                    logger.warning(
                        f"Server error likely transient. Retrying in {wait_time} seconds..."
                    )
                    time.sleep(wait_time)
                else:
                    self.tts_error.emit(
                        f"API Error: {e.message} (Status code: {e.status_code})"
                    )
                    return False  # Non-retryable or final attempt failed

            except OpenAIError as e:  # Catch broader OpenAI errors
                logger.error(f"General OpenAI error on attempt {attempt + 1}: {e}")
                # These might indicate config issues, not usually retryable
                self.tts_error.emit(f"OpenAI Error: {e}")
                return False

            except IOError as e:
                logger.exception(
                    f"File I/O error saving chunk {filename} on attempt {attempt+1}: {e}"
                )
                self.tts_error.emit(f"File saving error: {e}")
                return False  # Likely permissions or disk space issue, don't retry

            except Exception as e:
                # Catch unexpected errors during the process
                logger.exception(
                    f"Unexpected error saving chunk {filename} on attempt {attempt + 1}: {e}"
                )
                self.tts_error.emit(f"Unexpected error: {e}")
                return False  # Unexpected error, stop processing

        # If loop finishes without returning True, all retries failed
        logger.error(
            f"Failed to save chunk {filename} after {config.MAX_RETRIES} attempts."
        )
        self.tts_error.emit(
            f"Failed to generate audio chunk after multiple retries. See logs for details."
        )
        return False
