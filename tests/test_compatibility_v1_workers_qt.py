from __future__ import annotations

import pytest
from PyQt6.QtCore import QMetaMethod, QObject

from openai_tts_gui.gui import TTSWorker
from openai_tts_gui.tts import TTSProcessor
from tests.compatibility_v1_contracts import integer_mapping, load_manifest, mapping, strings


def _signal_arities(worker: TTSWorker, names: list[str]) -> dict[str, int]:
    meta_object = worker.metaObject()
    arities: dict[str, int] = {}
    for index in range(meta_object.methodCount()):
        method = meta_object.method(index)
        name = bytes(method.name()).decode()
        if name in names and method.methodType() is QMetaMethod.MethodType.Signal:
            arities[name] = method.parameterCount()
    return arities


def test_v1_worker_constructor_parent_params_cancel_and_signal_arities() -> None:
    worker_contract = mapping(load_manifest()["worker"])
    signals = integer_mapping(worker_contract["signals"])
    signal_names = list(signals)
    params = {"text": "compatibility"}
    positional_parent = QObject()
    keyword_parent = QObject()
    positional_worker = TTSWorker(params, positional_parent)
    keyword_worker = TTSWorker(params=params, parent=keyword_parent)

    worker_pairs = (
        (positional_worker, positional_parent),
        (keyword_worker, keyword_parent),
    )
    for worker, parent in worker_pairs:
        assert worker.parent() is parent
        assert worker.params is params
        assert _signal_arities(worker, signal_names) == signals
        assert worker.cancel() is None


def test_v1_worker_emits_exactly_one_terminal_signal(qtbot) -> None:
    worker_contract = mapping(load_manifest()["worker"])
    terminal_signals = strings(worker_contract["terminal_signals"])
    worker = TTSWorker(
        {
            "api_key": "compatibility-key",
            "text": " ",
            "output_path": "out.mp3",
            "model": "tts-1",
            "voice": "alloy",
            "response_format": "mp3",
            "speed": 1.0,
        }
    )
    terminal: list[str] = []
    worker.tts_complete.connect(lambda _message: terminal.append("tts_complete"))
    worker.tts_error.connect(lambda _message: terminal.append("tts_error"))
    worker.cancel()

    with qtbot.waitSignal(worker.finished, timeout=2_000):
        worker.start()

    assert set(terminal) <= set(terminal_signals)
    assert terminal == ["tts_error"]


@pytest.mark.parametrize("keyword_params", [False, True])
def test_v1_tts_processor_inherits_worker_construction_and_signals(keyword_params: bool) -> None:
    worker_contract = mapping(load_manifest()["worker"])
    signals = integer_mapping(worker_contract["signals"])
    signal_names = list(signals)
    params = {"text": "compatibility"}
    parent = QObject()
    if keyword_params:
        processor = TTSProcessor(params=params, parent=parent)
    else:
        processor = TTSProcessor(params, parent)

    assert TTSProcessor.__bases__ == (TTSWorker,)
    assert processor.parent() is parent
    assert processor.params is params
    assert _signal_arities(processor, signal_names) == signals
    assert processor.cancel() is None


def test_v1_worker_projection_check_rejects_missing_projection() -> None:
    missing_projection = type("MissingTTSProcessor", (), {})

    with pytest.raises(AssertionError):
        assert issubclass(missing_projection, TTSWorker)
