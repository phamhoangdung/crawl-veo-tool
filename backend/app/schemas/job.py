from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.job import JobStatus, Platform
from app.models.video import VideoStatus


class JobCreateRequest(BaseModel):
    platform: Platform
    keyword: str
    # Bilibili is a Chinese platform: searching verbatim Vietnamese almost never
    # returns results, so translating the keyword to Simplified Chinese is allowed.
    translate_keyword: bool = False


class SelectedVideo(BaseModel):
    """1 video the user selected on the Trending page — metadata taken from the list."""

    bvid: str
    title: str
    author_name: str | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None
    # Phase 22: real channel id — filled alongside author_name when creating the Video.
    channel_id: str | None = None


class JobFromSelectionRequest(BaseModel):
    videos: list[SelectedVideo]
    # Phase 20: the Discovery screen downloads right away on "Download selected videos" — previously
    # it only created a job and stayed silent, and no screen could show it again (see
    # docs/phases/phase-20-discovery-workspace.md section "Khảo sát" point 1). The flag can still
    # be turned off (default True) for other future callers that want to
    # only create the job without downloading right away.
    download: bool = True


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    platform_video_id: str
    title: str
    author_name: str | None
    duration_seconds: int | None
    cover_url: str | None
    source_url: str
    status: VideoStatus
    created_at: datetime
    # Only set in the search flow: this video was already in the library (not
    # just added by this job). Defaults to False for other flows.
    already_in_library: bool = False


class JobPageRead(BaseModel):
    """1 page of videos loaded into the job — used for infinite scroll on the Crawl page."""

    videos: list[VideoRead]
    page: int
    has_more: bool


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    keyword: str
    status: JobStatus
    created_at: datetime


class JobWithVideosRead(JobRead):
    # Read from `result_videos` (all Bilibili results, including videos already in the
    # library) when the service sets that attribute; otherwise falls back to `videos` as before —
    # other flows (from-selection) do not set `result_videos`.
    videos: list[VideoRead] = Field(validation_alias=AliasChoices("result_videos", "videos"))
    # Not stored in the DB — only set temporarily in create_bilibili_crawl_job so the frontend can warn
    # when keyword translation fails (searching verbatim gives almost 0 results).
    translation_failed: bool = False
    # Number of videos in the results already in the library — still shown in full, only so the
    # UI can mark them "downloaded" instead of hiding them.
    already_in_library: int = 0
    total_found: int = 0
