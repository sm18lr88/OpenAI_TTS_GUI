from __future__ import annotations

__all__ = ["TTSProcessor", "TTSService", "compute_backoff"]


def __getattr__(name: str):
    contract_names = {
        "CancellationStage",
        "CancelledOutcome",
        "CancelRequested",
        "ChunkCompleted",
        "ChunkFailureOutcome",
        "ChunkStarted",
        "DestinationChangedOutcome",
        "FfmpegStarted",
        "GenerationConfig",
        "GenerationHooks",
        "GenerationOutcome",
        "GenerationProgress",
        "GenerationRequest",
        "OutputBusyOutcome",
        "ProviderFailureOutcome",
        "ProviderReceipt",
        "ProviderRequest",
        "PublicationFailureOutcome",
        "PublicationInProgress",
        "PublicationRecoveryFailureOutcome",
        "FfmpegFailureOutcome",
        "FfmpegNotFoundOutcome",
        "PublicationStarted",
        "RetryWaiting",
        "RunAccounting",
        "RunStarted",
        "SuccessOutcome",
        "UnknownFailureOutcome",
    }
    if name in contract_names:
        from . import _contracts

        return getattr(_contracts, name)
    if name in {
        "DestinationObservation",
        "DestinationPaths",
        "ExistingResource",
        "MissingResource",
        "ResourceIdentity",
        "ResourceObservation",
        "destination_paths",
        "observe_destination",
    }:
        from . import _destination

        return getattr(_destination, name)
    if name == "RunState":
        from ._run_state import RunState

        return RunState
    if name in {"OpenAIProviderAdapter", "SpeechProvider"}:
        from ._provider import OpenAIProviderAdapter, SpeechProvider

        providers = {
            "OpenAIProviderAdapter": OpenAIProviderAdapter,
            "SpeechProvider": SpeechProvider,
        }
        return providers[name]
    if name in {"TTSService", "compute_backoff", "_compute_backoff"}:
        from ._service import TTSService, compute_backoff

        return {
            "TTSService": TTSService,
            "compute_backoff": compute_backoff,
            "_compute_backoff": compute_backoff,
        }[name]
    if name == "TTSProcessor":
        from ._compat import TTSProcessor

        return TTSProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
