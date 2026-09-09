from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.generated_asset import GeneratedAsset, GeneratedAssetType
from app.models.user import User
from app.services import ai_generation_service as service
from app.services import character_reference_service, cost_service

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch) -> Path:
    """Tách hẳn thư mục output khỏi storage thật để test không rác vào máy."""
    out = tmp_path / "generated"
    refs = tmp_path / "refs"
    out.mkdir()
    refs.mkdir()
    monkeypatch.setattr(service, "output_dir", lambda: out)
    monkeypatch.setattr(character_reference_service, "references_dir", lambda: refs)
    return out


@pytest.fixture
def fake_adapter(monkeypatch) -> dict:
    """Đếm số lần adapter thực sự được gọi — dùng để chứng minh cache KHÔNG gọi API."""
    calls = {"image": 0, "video": 0}

    async def fake_image(prompt, output_path, **kwargs):
        calls["image"] += 1
        Path(output_path).write_bytes(_PNG)

    async def fake_video(prompt, output_path, **kwargs):
        calls["video"] += 1
        Path(output_path).write_bytes(b"fake-mp4")

    monkeypatch.setattr(service.fake_adapter, "generate_image", fake_image)
    monkeypatch.setattr(service.fake_adapter, "generate_video", fake_video)
    return calls


def _make_ref(db: Session, name: str = "hero"):
    return character_reference_service.create_reference(db, 1, name, [("a.png", _PNG)])


class TestGenerateKeyframe:
    @pytest.mark.asyncio
    async def test_saves_asset_with_reference_link(self, db: Session, fake_adapter) -> None:
        ref = _make_ref(db)

        result = await service.generate_keyframe(db, 1, f"@{ref.name} at the counter")

        assert result.from_cache is False
        assert result.asset.type is GeneratedAssetType.IMAGE
        assert result.asset.source_character_ref_id == ref.id
        assert Path(result.asset.file_path).exists()
        assert fake_adapter["image"] == 1

    @pytest.mark.asyncio
    async def test_rejects_prompt_mentioning_unknown_reference(
        self, db: Session, fake_adapter
    ) -> None:
        """Sai tên ref phải chặn TRƯỚC khi gọi API — nếu để đi qua, người dùng trả
        tiền cho ảnh sinh ra thiếu nhân vật mình cần."""
        with pytest.raises(service.GenerationError, match="khong_co"):
            await service.generate_keyframe(db, 1, "@khong_co at the counter")

        assert fake_adapter["image"] == 0

    @pytest.mark.asyncio
    async def test_second_identical_call_reuses_asset_without_calling_adapter(
        self, db: Session, fake_adapter
    ) -> None:
        """Dedupe là cơ chế chống đốt tiền chính: refresh trang rồi bấm lại không
        được tính phí lần nữa."""
        ref = _make_ref(db)
        prompt = f"@{ref.name} at the counter"

        first = await service.generate_keyframe(db, 1, prompt)
        second = await service.generate_keyframe(db, 1, prompt)

        assert second.from_cache is True
        assert second.asset.id == first.asset.id
        assert fake_adapter["image"] == 1

    @pytest.mark.asyncio
    async def test_different_prompt_is_not_cached(self, db: Session, fake_adapter) -> None:
        ref = _make_ref(db)

        await service.generate_keyframe(db, 1, f"@{ref.name} scene one")
        second = await service.generate_keyframe(db, 1, f"@{ref.name} scene two")

        assert second.from_cache is False
        assert fake_adapter["image"] == 2

    @pytest.mark.asyncio
    async def test_cache_ignored_when_file_was_cleaned_up(
        self, db: Session, fake_adapter
    ) -> None:
        """storage_cleanup_service có thể xoá file nhưng record còn — coi như chưa
        cache, nếu không người dùng nhận về asset trỏ tới file không tồn tại."""
        ref = _make_ref(db)
        prompt = f"@{ref.name} at the counter"
        first = await service.generate_keyframe(db, 1, prompt)
        Path(first.asset.file_path).unlink()

        second = await service.generate_keyframe(db, 1, prompt)

        assert second.from_cache is False
        assert fake_adapter["image"] == 2


class TestGenerateVideoClip:
    @pytest.mark.asyncio
    async def test_requires_image_asset_as_keyframe(self, db: Session, fake_adapter) -> None:
        ref = _make_ref(db)
        image = await service.generate_keyframe(db, 1, f"@{ref.name} scene")
        video = await service.generate_video_clip(
            db, 1, "push in", keyframe_start_asset_id=image.asset.id
        )

        with pytest.raises(service.GenerationError, match="không phải ảnh"):
            await service.generate_video_clip(
                db, 1, "push in", keyframe_start_asset_id=video.asset.id
            )

    @pytest.mark.asyncio
    async def test_end_keyframe_changes_cache_key(self, db: Session, fake_adapter) -> None:
        """start→end (frame-to-frame) là yêu cầu khác với chỉ start — không được
        trả về cùng 1 clip đã cache."""
        ref = _make_ref(db)
        a = await service.generate_keyframe(db, 1, f"@{ref.name} scene a")
        b = await service.generate_keyframe(db, 1, f"@{ref.name} scene b")

        first = await service.generate_video_clip(
            db, 1, "push in", keyframe_start_asset_id=a.asset.id
        )
        second = await service.generate_video_clip(
            db,
            1,
            "push in",
            keyframe_start_asset_id=a.asset.id,
            keyframe_end_asset_id=b.asset.id,
        )

        assert second.from_cache is False
        assert second.asset.id != first.asset.id

    @pytest.mark.asyncio
    async def test_records_duration(self, db: Session, fake_adapter) -> None:
        ref = _make_ref(db)
        image = await service.generate_keyframe(db, 1, f"@{ref.name} scene")

        result = await service.generate_video_clip(
            db, 1, "push in", keyframe_start_asset_id=image.asset.id, duration_seconds=8.0
        )

        assert result.asset.duration_seconds == 8.0


class TestCostGuards:
    def test_per_call_threshold_blocks_until_confirmed(self, db: Session) -> None:
        with pytest.raises(service.CostThresholdExceededError):
            service._guard_cost(db, 1, 3.2, False)

        service._guard_cost(db, 1, 3.2, True)  # xác nhận rồi thì cho qua

    def test_under_threshold_passes(self, db: Session) -> None:
        service._guard_cost(db, 1, 0.5, False)

    def test_monthly_budget_blocks_even_when_confirmed(self, db: Session) -> None:
        """Hạn mức tháng là chốt cứng, khác ngưỡng mỗi lần gọi (chỉ là cảnh báo) —
        đây là thứ duy nhất chặn được agent chạy tự động qua đêm."""
        db.add(
            GeneratedAsset(
                user_id=1,
                type=GeneratedAssetType.VIDEO,
                file_path="/tmp/x.mp4",
                prompt="p",
                provider="falai",
                model="veo-3.1",
                cost_estimate_usd=29.5,
            )
        )
        db.commit()

        with pytest.raises(cost_service.MonthlyBudgetExceededError):
            service._guard_cost(db, 1, 1.0, True)

    def test_spending_from_previous_month_does_not_count(self, db: Session) -> None:
        last_month = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
        db.add(
            GeneratedAsset(
                user_id=1,
                type=GeneratedAssetType.VIDEO,
                file_path="/tmp/x.mp4",
                prompt="p",
                provider="falai",
                model="veo-3.1",
                cost_estimate_usd=100.0,
                created_at=last_month,
            )
        )
        db.commit()

        assert cost_service.spent_this_month_usd(db, 1) == 0.0


class TestKenBurns:
    def test_creates_free_video_asset_from_image(self, db: Session, monkeypatch) -> None:
        """Đường miễn phí: phải lưu như 1 GeneratedAsset video bình thường để dùng
        được ở thư viện video nền và timeline editor, nhưng chi phí bằng 0."""
        rendered: dict = {}

        def fake_ken_burns(image_path, output_path, **kwargs):
            rendered["called"] = True
            rendered["motion"] = kwargs.get("motion")
            Path(output_path).write_bytes(b"fake-mp4")

        monkeypatch.setattr(service.ffmpeg, "make_ken_burns_clip", fake_ken_burns)

        ref = _make_ref(db)
        image = service._save_asset(
            db,
            1,
            asset_type=GeneratedAssetType.IMAGE,
            file_path=Path(service.output_dir() / "img.png"),
            prompt="p",
            provider="falai-fake",
            model="fake-image",
            cost_usd=0.0,
            request_hash=None,
            character_ref_id=ref.id,
        )
        Path(image.file_path).write_bytes(_PNG)

        result = service.make_ken_burns_clip(
            db, 1, keyframe_asset_id=image.id, duration_seconds=3.0, motion="pan_right"
        )

        assert rendered["called"] is True
        assert rendered["motion"] == "pan_right"
        assert result.asset.type is GeneratedAssetType.VIDEO
        assert result.asset.cost_estimate_usd == 0.0
        assert result.asset.provider == service.PROVIDER_KEN_BURNS


class TestOutputNaming:
    @pytest.mark.asyncio
    async def test_prefix_numbers_assets_sequentially(self, db: Session, fake_adapter) -> None:
        """Đặt tên theo tập (EP001_001, EP001_002...) để quản lý output theo dự án."""
        ref = _make_ref(db)

        first = await service.generate_keyframe(
            db, 1, f"@{ref.name} scene a", output_prefix="EP001"
        )
        second = await service.generate_keyframe(
            db, 1, f"@{ref.name} scene b", output_prefix="EP001"
        )

        assert Path(first.asset.file_path).name == "EP001_001.png"
        assert Path(second.asset.file_path).name == "EP001_002.png"
        assert second.asset.sequence_no == 2

    @pytest.mark.asyncio
    async def test_without_prefix_uses_unique_name(self, db: Session, fake_adapter) -> None:
        ref = _make_ref(db)

        result = await service.generate_keyframe(db, 1, f"@{ref.name} scene")

        assert Path(result.asset.file_path).name.startswith("image_")
        assert result.asset.sequence_no is None


class TestExportToAssetLibrary:
    @pytest.mark.asyncio
    async def test_copies_clip_into_shared_store(
        self, db: Session, fake_adapter, tmp_path, monkeypatch
    ) -> None:
        """Kho dùng chung (`asset_service`) là nguồn của AssetPicker trong Timeline
        Editor — export xong thì clip ghép được như mọi file khác."""
        store = tmp_path / "assets"
        store.mkdir()
        monkeypatch.setattr(service.asset_service, "assets_dir", lambda: store)

        ref = _make_ref(db)
        image = await service.generate_keyframe(db, 1, f"@{ref.name} scene")
        clip = await service.generate_video_clip(
            db, 1, "push in", keyframe_start_asset_id=image.asset.id
        )

        imported = service.export_to_asset_library(db, 1, clip.asset.id)

        assert imported.kind == "video"
        assert Path(imported.path).exists()
        # Bản gốc phải còn để cache `request_hash` tiếp tục có hiệu lực.
        assert Path(clip.asset.file_path).exists()

    def test_rejects_unknown_asset(self, db: Session) -> None:
        with pytest.raises(service.GenerationError, match="Không tìm thấy asset"):
            service.export_to_asset_library(db, 1, 999)

    @pytest.mark.asyncio
    async def test_rejects_asset_whose_file_is_gone(
        self, db: Session, fake_adapter, tmp_path, monkeypatch
    ) -> None:
        store = tmp_path / "assets"
        store.mkdir()
        monkeypatch.setattr(service.asset_service, "assets_dir", lambda: store)

        ref = _make_ref(db)
        image = await service.generate_keyframe(db, 1, f"@{ref.name} scene")
        Path(image.asset.file_path).unlink()

        with pytest.raises(service.GenerationError, match="không còn trên ổ đĩa"):
            service.export_to_asset_library(db, 1, image.asset.id)


class TestListAssets:
    @pytest.mark.asyncio
    async def test_filters_by_type(self, db: Session, fake_adapter) -> None:
        ref = _make_ref(db)
        image = await service.generate_keyframe(db, 1, f"@{ref.name} scene")
        await service.generate_video_clip(
            db, 1, "push in", keyframe_start_asset_id=image.asset.id
        )

        images = service.list_assets(db, 1, GeneratedAssetType.IMAGE)
        videos = service.list_assets(db, 1, GeneratedAssetType.VIDEO)

        assert len(images) == 1
        assert len(videos) == 1
        assert len(service.list_assets(db, 1)) == 2
