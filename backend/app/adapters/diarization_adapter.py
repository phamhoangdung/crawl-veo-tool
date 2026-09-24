import logging
from pathlib import Path

import numpy as np
import torch
from pydub import AudioSegment
from sklearn.cluster import AgglomerativeClustering

from app.core.config import BACKEND_DIR, app_data_dir, is_frozen

logger = logging.getLogger(__name__)

_MODEL = None

# Dưới ngưỡng này (cosine distance) coi 2 đoạn là cùng 1 người nói. Chọn theo
# mức phổ biến với ECAPA-TDNN/voxceleb — cần chỉnh lại nếu test video thật cho
# kết quả tách nhầm quá nhiều/quá ít vai (xem docs/phases/phase-19-multi-speaker-dubbing.md).
_CLUSTER_DISTANCE_THRESHOLD = 0.7

# ECAPA cần input đủ dài để cho embedding ổn định — đoạn ngắn hơn được pad im lặng.
_MIN_CLIP_MS = 300


def _model_cache_dir() -> Path:
    base = app_data_dir() if is_frozen() else BACKEND_DIR
    return base / "storage" / "models" / "spkrec-ecapa-voxceleb"


def _get_model():
    global _MODEL
    if _MODEL is None:
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _MODEL = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(_model_cache_dir()),
            # Mặc định SpeechBrain tạo symlink — trên Windows cần quyền admin hoặc
            # bật Developer Mode, máy người dùng thường không có -> lỗi tải model.
            local_strategy=LocalStrategy.COPY,
            run_opts={"device": device},
        )
    return _MODEL


def _segment_embedding(
    model, audio: AudioSegment, start_s: float, end_s: float
) -> np.ndarray:
    clip = audio[int(start_s * 1000) : int(end_s * 1000)]
    if len(clip) < _MIN_CLIP_MS:
        clip = clip + AudioSegment.silent(duration=_MIN_CLIP_MS - len(clip))
    clip = clip.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    # Đọc thẳng mẫu âm thanh từ pydub thay vì ghi ra wav rồi `torchaudio.load`:
    # torchaudio 2.9+ chuyển sang bắt buộc cài `torchcodec` để đọc file, mà gói
    # đó nặng và không cần thiết cho việc này.
    samples = np.array(clip.get_array_of_samples(), dtype=np.float32) / 32768.0
    signal = torch.from_numpy(samples).unsqueeze(0)

    embedding = model.encode_batch(signal)
    return embedding.squeeze().detach().cpu().numpy()


def assign_speakers(audio_path: Path, segments: list[dict]) -> list[dict]:
    """Gắn nhãn SPEAKER_00/01/... vào từng segment dựa trên embedding giọng nói.

    Dùng SpeechBrain ECAPA-TDNN (mã nguồn mở, model public trên Hugging Face,
    KHÔNG cần đăng nhập/accept license như pyannote) thay vì WhisperX+pyannote —
    quyết định đổi hướng ở docs/phases/phase-19-multi-speaker-dubbing.md mục
    "Quyết định kỹ thuật". Đánh đổi: kém chính xác hơn pyannote với đoạn rất
    ngắn hoặc nhiều người nói chồng tiếng — chấp nhận được cho MVP video 2-4
    người nói rõ ràng.
    """
    if not segments:
        return []
    if len(segments) == 1:
        return [{**segments[0], "speaker": "SPEAKER_00"}]

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
