import numpy as np
from app.adapters import diarization_adapter


class TestAssignSpeakers:
    def test_empty_segments_returns_empty(self) -> None:
        assert diarization_adapter.assign_speakers("unused.wav", []) == []

    def test_single_segment_gets_speaker_00(self) -> None:
        segments = [{"start": 0.0, "end": 1.0, "text": "hi"}]
        result = diarization_adapter.assign_speakers("unused.wav", segments)
        assert result == [
            {"start": 0.0, "end": 1.0, "text": "hi", "speaker": "SPEAKER_00"}
        ]

    def test_clusters_two_distinct_voices(self, monkeypatch) -> None:
        """4 segments, 2 clearly distinct voices (simulated embeddings in 2 very different corners) —
        does not load the real model, only verifies the clustering logic + correct labeling."""
        segments = [
            {"start": 0.0, "end": 1.0, "text": "a"},
            {"start": 1.0, "end": 2.0, "text": "b"},
            {"start": 2.0, "end": 3.0, "text": "c"},
            {"start": 3.0, "end": 4.0, "text": "d"},
        ]
        fake_embeddings = {
            0.0: np.array([1.0, 0.0]),
            1.0: np.array([1.0, 0.01]),
            2.0: np.array([0.0, 1.0]),
            3.0: np.array([0.01, 1.0]),
        }

        monkeypatch.setattr(diarization_adapter, "_get_model", lambda: object())
        monkeypatch.setattr(
            diarization_adapter,
            "_segment_embedding",
            lambda _model, _audio, start, _end: fake_embeddings[start],
        )
        monkeypatch.setattr(
            diarization_adapter.AudioSegment, "from_file", lambda _path: object()
        )

        result = diarization_adapter.assign_speakers("unused.wav", segments)

        speakers = [seg["speaker"] for seg in result]
        assert speakers[0] == speakers[1]
        assert speakers[2] == speakers[3]
        assert speakers[0] != speakers[2]
        # The original segment does not lose fields when speaker is added.
        assert result[0]["text"] == "a"
