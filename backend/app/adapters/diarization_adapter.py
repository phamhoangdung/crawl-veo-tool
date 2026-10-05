import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydub import AudioSegment

from app.core import packs
from app.core.config import BACKEND_DIR, app_data_dir, is_frozen

if TYPE_CHECKING:
    import numpy as np

# numpy/torch/sklearn live in the downloadable AI pack (app/core/packs.py), so they
# are imported inside the functions, after `packs.require_ai()`.

logger = logging.getLogger(__name__)

_MODEL = None

# Below this threshold (cosine distance) two segments count as the same speaker. Chosen from
# common values for ECAPA-TDNN/voxceleb — needs retuning if testing on real video shows
# too many/too few speakers (see docs/phases/phase-19-multi-speaker-dubbing.md).
_CLUSTER_DISTANCE_THRESHOLD = 0.7

# ECAPA needs long enough input for a stable embedding — shorter segments are padded with silence.
_MIN_CLIP_MS = 300


def _model_cache_dir() -> Path:
    base = app_data_dir() if is_frozen() else BACKEND_DIR
    return base / "storage" / "models" / "spkrec-ecapa-voxceleb"


def _get_model():
    global _MODEL
    if _MODEL is None:
        packs.require_ai()
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _MODEL = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(_model_cache_dir()),
            # By default SpeechBrain creates symlinks — on Windows that needs admin or
            # Developer Mode, which regular user machines lack -> model download error.
            local_strategy=LocalStrategy.COPY,
            run_opts={"device": device},
        )
    return _MODEL


def _segment_embedding(
    model, audio: AudioSegment, start_s: float, end_s: float
) -> "np.ndarray":
    import numpy as np
    import torch

    clip = audio[int(start_s * 1000) : int(end_s * 1000)]
    if len(clip) < _MIN_CLIP_MS:
        clip = clip + AudioSegment.silent(duration=_MIN_CLIP_MS - len(clip))
    clip = clip.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    # Read the audio samples straight from pydub instead of writing a wav and calling `torchaudio.load`:
    # torchaudio 2.9+ now requires `torchcodec` to read files, and that package
    # is heavy and unnecessary for this.
    samples = np.array(clip.get_array_of_samples(), dtype=np.float32) / 32768.0
    signal = torch.from_numpy(samples).unsqueeze(0)

    embedding = model.encode_batch(signal)
    return embedding.squeeze().detach().cpu().numpy()


def assign_speakers(audio_path: Path, segments: list[dict]) -> list[dict]:
    """Attach SPEAKER_00/01/... labels to each segment based on voice embeddings.

    Uses SpeechBrain ECAPA-TDNN (open source, public model on Hugging Face,
    NO login/license acceptance needed like pyannote) instead of WhisperX+pyannote —
    the change of direction is recorded in docs/phases/phase-19-multi-speaker-dubbing.md, section
    "Quyết định kỹ thuật". Trade-off: less accurate than pyannote on very
    short segments or overlapping speakers — acceptable for an MVP with videos of 2-4
    clearly distinct speakers.
    """
    if not segments:
        return []
    if len(segments) == 1:
        return [{**segments[0], "speaker": "SPEAKER_00"}]

    packs.require_ai()
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    model = _get_model()
    audio = AudioSegment.from_file(audio_path)
    embeddings = np.stack(
        [_segment_embedding(model, audio, seg["start"], seg["end"]) for seg in segments]
    )

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=_CLUSTER_DISTANCE_THRESHOLD,
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(embeddings)
    return [
        {**seg, "speaker": f"SPEAKER_{int(label):02d}"}
        for seg, label in zip(segments, labels)
    ]
