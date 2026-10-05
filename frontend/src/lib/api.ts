import axios from 'axios'

declare global {
  interface Window {
    /** The packaged build (Tauri) injects the real backend address — the port is chosen at runtime. */
    __VIEDUB_API_BASE__?: string
  }
}

export const API_BASE_URL =
  window.__VIEDUB_API_BASE__ ??
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE_URL,
})

/**
 * Extract `detail` from the HTTP error the backend returns (FastAPI `HTTPException` always has
 * the shape `{"detail": "..."}`), falling back to `fallback` when it is not an axios error or
 * the response has no `detail`. Shared instead of every place writing its own — previously
 * some places used `axios.isAxiosError` (correct) and others hand-checked
 * like `'response' in error` (weaker, cannot rule out a non-HTTP error that happens to have a
 * field named `response`).
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback
  const detail = (error.response?.data as { detail?: string } | undefined)
    ?.detail
  return detail || fallback
}

export type Platform = 'bilibili' | 'douyin' | 'local'

export type VideoStatus =
  | 'queued'
  | 'downloading'
  | 'downloaded'
  | 'separating_audio'
  | 'transcribing'
  | 'transcribed'
  | 'translating'
  | 'translated'
  | 'dubbing'
  | 'muxing'
  | 'done'
  | 'paused_quota'
  | 'failed_download'
  | 'failed_separating_audio'
  | 'failed_transcribing'
  | 'failed_translating'
  | 'failed_dubbing'
  | 'failed_muxing'

export interface VideoRead {
  id: number
  platform: Platform
  platform_video_id: string
  title: string
  author_name: string | null
  duration_seconds: number | null
  cover_url: string | null
  source_url: string
  status: VideoStatus
  created_at: string
  /** Video already in the library from before (only present in search results). */
  already_in_library?: boolean
}

export interface JobWithVideosRead {
  id: number
  platform: Platform
  keyword: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  created_at: string
  videos: VideoRead[]
  translation_failed: boolean
  /** Number of videos in the results already in the library — still shown in full, only to
   *  mark them "downloaded" instead of hiding them. */
  already_in_library: number
  total_found: number
}

export interface TrendingCategory {
  rid: number
  name: string
  name_zh: string | null
  group: string | null
  is_followed: boolean
}

export interface SnapshotPoint {
  rid: number
  captured_at: string
  total_plays: number
  avg_plays: number
  /** Total `pts` score (computed by Bilibili) — more reliable than total_plays for
   * comparing "hotness" between categories, see backend `schemas/trending.py`. */
  total_pts: number
  heat_score: number
}

export interface CategoryHistory {
  rid: number
  name: string
  points: SnapshotPoint[]
}

export type TaskKind =
  | 'download'
  | 'transcribe'
  | 'translate'
  | 'diarize'
  | 'dub'
  | 'burn'
  | 'render_project'

/** Whether a task belongs to 1 video (crawl pipeline) or 1 multi-scene project (Phase 16). */
export type TaskSubjectType = 'video' | 'project'

export interface TaskProgress {
  /** With subject_type='project' this is the project_id — the backend keeps the name of the
   *  field so every place already using it needs no change. */
  video_id: number
  subject_type: TaskSubjectType
  title: string
  kind: TaskKind
  kind_label: string
  stage: string
  stage_label: string
  percent: number
  current: number
  total: number | null
  is_running: boolean
  speed_per_sec: number
  error: string | null
}

export interface FileEntry {
  variant: 'original' | 'dubbed' | 'burned'
  path: string
  size_bytes: number
  exists: boolean
}

export interface VideoFiles {
  video_id: number
  title: string
  status: VideoStatus
  /** Cover image from the original platform. The backend (`VideoFilesRead`) always returned this field,
   * only the type here was missing it — so 3 places using it got tsc errors. */
  cover_url: string | null
  video_dir: string | null
  files: FileEntry[]
  total_bytes: number
}

export interface DashboardStats {
  total_videos: number
  downloaded: number
  transcribed: number
  translated: number
  dubbed: number
  failed: number
  total_bytes: number
  running_tasks: number
}

export interface StorageSummary {
  storage_root: string
  video_count: number
  total_bytes: number
  orphan_bytes: number
}

export interface StorageLocation {
  storage_root: string
  video_path: string | null
  video_dir: string | null
  exists: boolean
}

export interface TrendingPage {
  videos: TrendingVideo[]
  page: number
  has_more: boolean
  /** "ranking" = the real per-category ranking; "popular" = the site-wide popular list
   * ("All" tab, with real pagination); "search" = search by keyword (the category name
   * when scrolling past page 1, or the free search box) — broader
   * but may mix in unrelated videos. The UI displays them differently. */
  source: 'ranking' | 'popular' | 'search'
  /** Only meaningful when `source==='search'` and keyword translation is on — if translation
   * failed it already fell back to verbatim search; reported so the user can be warned. */
  translation_failed?: boolean
  /** Phase 22: true when the source was blocked by Bilibili risk control (only the "other videos
   * in the channel" page) — very different from a truly empty list, the UI must show a degraded-state
   * message instead of "this channel has no videos". */
  degraded?: boolean
}

export interface CategoryStats {
  rid: number
  name: string
  group: string | null
  video_count: number
  total_plays: number
  avg_plays: number
  max_plays: number
  total_likes: number
  /** Total `pts` score — the main metric for comparing "hotness" between categories. */
  total_pts: number
  top_video_title: string | null
}

export interface TrendingVideo {
  bvid: string
  title: string
  author_name: string | null
  play_count: number | null
  like_count: number | null
  duration_seconds: number | null
  cover_url: string | null
  comment_count: number | null
  danmaku_count: number | null
  coin_count: number | null
  /** Bilibili's real ranking score — only present when the video comes from the ranking
   * (source: "ranking"). null means this video is from search, not truly
   * trending. */
  heat_score: number | null
  published_at: string | null
  /** Real id in the DB — meaning this video has been downloaded before (Phase 20, Discovery
   * screen). `null` = never downloaded. */
  video_id: number | null
  already_in_library: boolean
  /** Real channel id (Bilibili: mid as a string) — Phase 22. `null` if the API
   * does not return it (rare). */
  channel_id: string | null
  channel_is_followed: boolean
}

/** YouTube is ONLY used to watch trends/score topics — it does not download videos (unlike
 * Bilibili/Douyin). See docs/phases/phase-17-content-opportunity.md. */
export interface YoutubeCategory {
  id: string
  name: string
}

export interface YoutubeVideo {
  video_id: string
  title: string
  channel_title: string
  thumbnail_url: string | null
  view_count: number | null
  like_count: number | null
  comment_count: number | null
  published_at: string | null
}

export interface YoutubeTrendingPage {
  videos: YoutubeVideo[]
  next_page_token: string | null
  has_more: boolean
}

export interface Topic {
  id: number
  name: string
  query: string
  note: string | null
  created_at: string
  score: number | null
  sample_video_count: number | null
  competition_count: number | null
  top_video_title: string | null
  top_video_url: string | null
  scored_at: string | null
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  translated_text: string
  /** Phase 19: speaker label (e.g. "SPEAKER_00") — empty means speaker separation has not run. */
  speaker: string
}

/** Phase 19: enough info for the backend to know which provider to call with which voice id. */
export interface VoiceRef {
  provider: string // "edge" | "elevenlabs"
  voice_id: string
}

export interface VoiceOption extends VoiceRef {
  name: string
  gender: string
}

export interface VideoDetail {
  id: number
  status: VideoStatus
  transcript: TranscriptSegment[]
  dubbed_path: string | null
  burned_path: string | null
  title: string | null
  author_name: string | null
  cover_url: string | null
  source_url: string | null
  duration_seconds: number | null
  local_path: string | null
  error_message: string | null
  speaker_voices: Record<string, VoiceRef>
}

export type ApiKeyStatus = 'active' | 'cooldown' | 'exhausted' | 'invalid'

export interface ApiKeyRead {
  id: number
  provider: string
  label: string | null
  masked_key: string
  status: ApiKeyStatus
  request_count: number
  error_count: number
  last_used_at: string | null
  cooldown_until: string | null
  updated_at: string
}

export interface LibraryItem {
  id: number
  title: string
  platform: Platform
  status: string
  has_dubbed: boolean
  has_burned: boolean
  created_at: string
}

export async function createCrawlJob(
  keyword: string,
  options: { platform?: Platform; translateKeyword?: boolean } = {}
) {
  const { platform = 'bilibili', translateKeyword = false } = options
  const { data } = await api.post<JobWithVideosRead>('/api/jobs', {
    keyword,
    platform,
    translate_keyword: translateKeyword,
  })
  return data
}

export interface JobPage {
  videos: VideoRead[]
  page: number
  has_more: boolean
}

/** Load one more page of search results into an existing job (infinite scroll on the Crawl page). */
export async function loadMoreJobVideos(jobId: number, page: number) {
  const { data } = await api.post<JobPage>(
    `/api/jobs/${jobId}/load-more`,
    null,
    {
      params: { page },
    }
  )
  return data
}

/** Create a download job from the videos the user ticked on the Trending page. */
export async function createJobFromSelection(videos: TrendingVideo[]) {
  const { data } = await api.post<JobWithVideosRead>(
    '/api/jobs/from-selection',
    {
      videos: videos.map((v) => ({
        bvid: v.bvid,
        title: v.title,
        author_name: v.author_name,
        duration_seconds: v.duration_seconds,
        cover_url: v.cover_url,
        channel_id: v.channel_id,
      })),
    }
  )
  return data
}

export async function getTrendingCategories() {
  const { data } = await api.get<TrendingCategory[]>(
    '/api/trending/bilibili/categories'
  )
  return data
}

export async function refreshCategories() {
  const { data } = await api.post<TrendingCategory[]>(
    '/api/trending/bilibili/categories/refresh'
  )
  return data
}

export async function getFollowedCategories() {
  const { data } = await api.get<number[]>(
    '/api/trending/bilibili/categories/followed'
  )
  return data
}

export async function setFollowedCategories(rids: number[]) {
  const { data } = await api.put<number[]>(
    '/api/trending/bilibili/categories/followed',
    {
      rids,
    }
  )
  return data
}

export async function getCategoryHistory(rids: number[], days = 30) {
  const { data } = await api.get<CategoryHistory[]>(
    '/api/trending/bilibili/history',
    {
      params: { rids: rids.join(','), days },
    }
  )
  return data
}

/** Progress of every running task: download, transcribe, translate, dub. */
export async function getTaskProgress() {
  const { data } = await api.get<TaskProgress[]>('/api/downloads/progress')
  return data
}

export async function clearTaskProgress(videoId: number, kind?: TaskKind) {
  await api.delete(`/api/downloads/progress/${videoId}`, {
    params: kind ? { kind } : undefined,
  })
}

export async function clearFinishedTasks() {
  const { data } = await api.delete<{ cleared: number }>(
    '/api/downloads/progress/finished'
  )
  return data
}

export async function getStorageLocation(videoId?: number) {
  const { data } = await api.get<StorageLocation>('/api/downloads/location', {
    params: videoId ? { video_id: videoId } : undefined,
  })
  return data
}

/** Open the folder containing the file in Finder/Explorer — only works because the tool is local. */
export async function revealInFileManager(videoId?: number) {
  const { data } = await api.post<{ opened: string }>(
    '/api/downloads/reveal',
    null,
    {
      params: videoId ? { video_id: videoId } : undefined,
    }
  )
  return data
}

/** 1 page of videos of a category — page 1 from the ranking, later pages from search. */
/** Bilibili only has 3-day and 7-day rankings (measured for real, other values are rejected). */
export type RankingDays = 3 | 7

export async function getCategoryPage(
  rid: number,
  page: number,
  day: RankingDays = 3
) {
  const { data } = await api.get<TrendingPage>(
    '/api/trending/bilibili/category-page',
    {
      params: { rid, page, day },
    }
  )
  return data
}

/** Site-wide popular list of Bilibili ("All" tab) — with real pagination. */
export async function getPopularPage(page: number) {
  const { data } = await api.get<TrendingPage>(
    '/api/trending/bilibili/popular',
    {
      params: { page },
    }
  )
  return data
}

/** Free search by any keyword, not limited to 1 category. */
export async function searchBilibili(
  keyword: string,
  page: number,
  options: { translateKeyword?: boolean } = {}
) {
  const { data } = await api.get<TrendingPage>(
    '/api/trending/bilibili/search',
    {
      params: {
        keyword,
        page,
        translate_keyword: options.translateKeyword ?? false,
      },
    }
  )
  return data
}

/** Related videos (Phase 22) — used for the "Similar videos" strip in the preview popup. */
export async function getRelatedVideos(bvid: string) {
  const { data } = await api.get<TrendingPage>(
    '/api/trending/bilibili/related',
    {
      params: { bvid },
    }
  )
  return data
}

/** Other videos of 1 channel (Phase 22) — may return `degraded: true` when
 * blocked by Bilibili risk control (measured: this risk is very high without a
 * login cookie) — the UI must show the proper degraded-state message. */
export async function getChannelVideos(channelId: string, page = 1) {
  const { data } = await api.get<TrendingPage>(
    `/api/trending/bilibili/channel/${channelId}/videos`,
    { params: { page } }
  )
  return data
}

export interface Channel {
  platform: string
  channel_id: string
  name: string
  avatar_url: string | null
  is_followed: boolean
}

export async function getFollowedChannels(platform = 'bilibili') {
  const { data } = await api.get<Channel[]>('/api/channels/followed', {
    params: { platform },
  })
  return data
}

export async function setChannelFollowed(
  platform: string,
  channelId: string,
  name: string,
  followed: boolean
) {
  const { data } = await api.put<Channel>(
    `/api/channels/${platform}/${channelId}/followed`,
    { followed },
    { params: { name } }
  )
  return data
}

export async function getCategoryStats(rids: number[]) {
  const { data } = await api.get<CategoryStats[]>(
    '/api/trending/bilibili/stats',
    {
      params: { rids: rids.join(',') },
    }
  )
  return data
}

export async function getTrendingRanking(rid: number) {
  const { data } = await api.get<TrendingVideo[]>(
    '/api/trending/bilibili/ranking',
    {
      params: { rid },
    }
  )
  return data
}

export async function getVideoDetail(videoId: number) {
  const { data } = await api.get<VideoDetail>(`/api/videos/${videoId}`)
  return data
}

export async function downloadVideo(videoId: number) {
  const { data } = await api.post<VideoDetail>(
    `/api/videos/${videoId}/download`
  )
  return data
}

export async function transcribeVideo(videoId: number) {
  const { data } = await api.post<VideoDetail>(
    `/api/videos/${videoId}/transcribe`
  )
  return data
}

export async function translateVideo(
  videoId: number,
  sourceLang = 'zh',
  targetLang = 'vi'
) {
  const { data } = await api.post<VideoDetail>(
    `/api/videos/${videoId}/translate`,
    {
      source_lang: sourceLang,
      target_lang: targetLang,
    }
  )
  return data
}

export async function updateTranscript(
  videoId: number,
  segments: TranscriptSegment[]
) {
  const { data } = await api.put<VideoDetail>(
    `/api/videos/${videoId}/transcript`,
    segments
  )
  return data
}

/** Detect how many different speakers there are and label each dialogue segment —
 * optional, if skipped `dubVideo` still runs with 1 shared voice. */
export async function diarizeVideo(videoId: number) {
  const { data } = await api.post<VideoDetail>(`/api/videos/${videoId}/diarize`)
  return data
}

/** Edge-TTS voices (always present) + the user's real ElevenLabs voices if a key is configured. */
export async function getAvailableVoices(videoId: number) {
  const { data } = await api.get<VoiceOption[]>(`/api/videos/${videoId}/voices`)
  return data
}

export async function updateSpeakerVoices(
  videoId: number,
  speakerVoices: Record<string, VoiceRef>
) {
  const { data } = await api.put<VideoDetail>(
    `/api/videos/${videoId}/speaker-voices`,
    speakerVoices
  )
  return data
}

export async function dubVideo(videoId: number, keepBackground = true) {
  const { data } = await api.post<VideoDetail>(
    `/api/videos/${videoId}/dub`,
    null,
    {
      params: { keep_background: keepBackground },
    }
  )
  return data
}

export interface BurnSubtitlesOptions {
  /** `'top'` when the source video already has burned-in subtitles at the bottom — left at the default, the two
   * text layers overlap. */
  position?: 'bottom' | 'top'
  /** Font id in `font_service.py` (backend) — leave empty to use the default font. */
  font_family?: string
  /** Hex without '#', e.g. 'FFFFFF'. */
  font_color?: string
  bold?: boolean
}

export async function burnSubtitles(
  videoId: number,
  options: BurnSubtitlesOptions = {}
) {
  const { data } = await api.post<VideoDetail>(
    `/api/videos/${videoId}/burn-subtitles`,
    null,
    { params: { position: 'bottom', ...options } }
  )
  return data
}

export async function getLibrary() {
  const { data } = await api.get<LibraryItem[]>('/api/library')
  return data
}

export function getDownloadUrl(
  videoId: number,
  variant: 'dubbed' | 'burned' | 'original'
) {
  return `${API_BASE_URL}/api/library/${videoId}/download?variant=${variant}`
}

export function getZipDownloadUrl(
  videoIds: number[],
  variant: 'dubbed' | 'burned' | 'original'
) {
  return `${API_BASE_URL}/api/library/download-zip?video_ids=${videoIds.join(',')}&variant=${variant}`
}

export async function getVideoFiles() {
  const { data } = await api.get<VideoFiles[]>('/api/files')
  return data
}

export async function getDashboardStats() {
  const { data } = await api.get<DashboardStats>('/api/files/dashboard-stats')
  return data
}

export async function getVideoFilesById(videoId: number) {
  const { data } = await api.get<VideoFiles>(`/api/files/${videoId}`)
  return data
}

export async function getStorageSummary() {
  const { data } = await api.get<StorageSummary>('/api/files/summary')
  return data
}

export async function deleteFileVariant(videoId: number, variant: string) {
  const { data } = await api.delete<{ deleted: boolean }>(
    `/api/files/${videoId}/${variant}`
  )
  return data
}

export async function deleteVideoFiles(videoId: number) {
  const { data } = await api.delete<{ freed_bytes: number }>(
    `/api/files/${videoId}`
  )
  return data
}

export async function cleanupOrphanFiles() {
  const { data } = await api.post<{ freed_bytes: number }>(
    '/api/files/cleanup-orphans'
  )
  return data
}

/** Delete job directories older than `maxAgeDays`. The same function the background cleanup loop calls —
 * this button is only to run it right now, without waiting for the 24h cycle. */
export async function cleanupOldJobs(maxAgeDays = 30) {
  const { data } = await api.post<{
    removed_job_ids: string[]
    max_age_days: number
  }>('/api/files/cleanup-old-jobs', null, {
    params: { max_age_days: maxAgeDays },
  })
  return data
}

// --- Douyin (Phase 3) ---
// Only configuration + probing exist so far. Video download is not done: the JSON shape of Douyin
// can only be known by a real call with a valid cookie, and writing the extraction by guesswork
// would create something that looks like it works but is wrong in a place nobody can verify.

export interface DouyinStatus {
  configured: boolean
  hint: string
}

export interface DouyinProbe {
  aweme_id: string
  top_level_keys: string[]
  detail_keys: string[]
}

export async function getDouyinStatus() {
  const { data } = await api.get<DouyinStatus>('/api/jobs/douyin/status')
  return data
}

export async function probeDouyinUrl(shareUrl: string) {
  const { data } = await api.post<DouyinProbe>('/api/jobs/douyin/probe', {
    share_url: shareUrl,
  })
  return data
}

// --- Run the pipeline in bulk (Phase 1/2) ---

export type BatchStep = 'download' | 'transcribe' | 'translate' | 'dub' | 'burn'

export interface BatchItem {
  video_id: number
  title: string
  status: string
  current_step: string | null
  error: string | null
}

export interface BatchStatus {
  id: string
  total: number
  done: number
  failed: number
  skipped: number
  running: number
  pending: number
  is_running: boolean
  cancelled: boolean
  steps: string[]
  items: BatchItem[]
}

export async function startBatch(
  videoIds: number[],
  steps?: BatchStep[],
  concurrency = 1
) {
  const { data } = await api.post<BatchStatus>('/api/batch/start', {
    video_ids: videoIds,
    steps: steps ?? null,
    concurrency,
  })
  return data
}

/** `null` when no batch has ever run in this backend run. */
export async function getBatchStatus() {
  const { data } = await api.get<BatchStatus | null>('/api/batch/status')
  return data
}

export async function cancelBatch() {
  const { data } = await api.post<{ cancelled: boolean }>('/api/batch/cancel')
  return data
}

/** Videos that have not finished the whole pipeline — the suggested input source for the next batch. */
export async function getPendingVideoIds(limit = 50) {
  const { data } = await api.get<number[]>('/api/batch/pending-videos', {
    params: { limit },
  })
  return data
}

export async function getApiKeys() {
  const { data } = await api.get<ApiKeyRead[]>('/api/api-keys')
  return data
}

export async function addApiKey(
  provider: string,
  apiKey: string,
  label?: string
) {
  const { data } = await api.post<ApiKeyRead>('/api/api-keys', {
    provider,
    api_key: apiKey,
    label: label || null,
  })
  return data
}

export async function updateApiKey(
  keyId: number,
  patch: { label?: string; status?: ApiKeyStatus }
) {
  const { data } = await api.patch<ApiKeyRead>(`/api/api-keys/${keyId}`, patch)
  return data
}

export async function deleteApiKey(keyId: number) {
  await api.delete(`/api/api-keys/${keyId}`)
}

// --- Phase 13: timeline editor ---
// The "clip" shape merges the fields of all 3 track types (video/audio/overlay) instead of
// a separate union type — simplifying drag-and-drop/patch operations in the store, matching the
// backend schema (dict[str, Any] per track, see app/schemas/timeline.py).
export interface TimelineClip {
  source?: string
  text?: string
  /** An image clip shown for the whole video leaves start/end empty; other kinds always have them. */
  start?: number
  end?: number
  track_start?: number
  volume?: number
  transition_in?: 'cut' | 'fade'
  transition_duration?: number
  x?: number
  y?: number
  font_size?: number
  /** Image track (logo/watermark) and blur region: width as a frame ratio [0,1]. */
  width?: number
  /** Blur region: height as a frame ratio [0,1]. */
  height?: number
  /** Blur region: strength (gblur sigma, or cell size when pixelate). */
  strength?: number
  /** Blur region: 'blur' smudges, 'pixelate' hides in squares (hides text better). */
  mode?: 'blur' | 'pixelate'
  /** Overlay text: limit of the subtitle box width as a ratio [0,1]; long sentences wrap automatically. */
  box_width?: number
  /** Image track: opacity [0,1] — a watermark usually uses 0.3-0.6. */
  opacity?: number
  /** Overlay text: font id in `font_service.py` (backend) — leave empty to use the default font. */
  font_family?: string
  /** Overlay text: text color as hex without '#', e.g. 'FFCC00'. */
  font_color?: string
  /** Overlay text: bold. */
  bold?: boolean
}

export interface TimelineTrack {
  type: 'video' | 'audio' | 'overlay' | 'image' | 'blur'
  role?: string
  clips: TimelineClip[]
}

export interface TimelineOperations {
  tracks: TimelineTrack[]
}

// --- Translate one-off text for the tooltip (cached in the backend) ---

export interface TranslateResult {
  translated_text: string
  cached: boolean
}

export async function translateText(
  text: string,
  sourceLang = 'zh',
  targetLang = 'vi'
) {
  const { data } = await api.post<TranslateResult>('/api/translate', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  })
  return data
}

/** Translate a whole page in 1 request — 40 separate requests would hit the rate limit. */
export async function translateBatch(
  texts: string[],
  sourceLang = 'zh',
  targetLang = 'vi'
) {
  const { data } = await api.post<{ translations: Record<string, string> }>(
    '/api/translate/batch',
    { texts, source_lang: sourceLang, target_lang: targetLang }
  )
  return data.translations
}

// --- Shared file library: logo, intro/outro, background music (Phase 9) ---
// Assets are reused by MANY videos so they are stored separately, not in a single video's directory.

export type AssetKind = 'image' | 'video' | 'audio'

export interface Asset {
  id: string
  name: string
  kind: AssetKind
  /** Absolute path on the machine — this is what goes into the clip's `source`. */
  path: string
  size: number
}

export async function listAssets(kind?: AssetKind) {
  const { data } = await api.get<Asset[]>('/api/assets', {
    params: kind ? { kind } : undefined,
  })
  return data
}

export async function uploadAsset(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<Asset>('/api/assets', form)
  return data
}

export async function deleteAsset(assetId: string) {
  await api.delete(`/api/assets/${assetId}`)
}

/** Preview URL (logo image, background music preview) — used directly in <img>/<audio>. */
export function assetFileUrl(assetId: string) {
  return `${API_BASE_URL}/api/assets/${assetId}/file`
}

// --- Bundled fonts for subtitles/watermark text (Phase 13) ---
// Shared by the Timeline Editor (overlay track) and burn_subtitles.

export interface Font {
  id: string
  label: string
}

export async function getFonts() {
  const { data } = await api.get<Font[]>('/api/fonts')
  return data
}

/** URL of the .ttf file — used as the `@font-face` source to preview the font before rendering. */
export function fontFileUrl(fontId: string) {
  return `${API_BASE_URL}/api/fonts/${fontId}/file`
}

export interface AudioStems {
  voice: string | null
  background: string | null
  mixed: string | null
}

/** Separated audio tracks, to adjust the narration and background music volume independently. */
export async function getAudioStems(videoId: number) {
  const { data } = await api.get<AudioStems>(
    `/api/videos/${videoId}/audio-stems`
  )
  return data
}

export async function getTimeline(videoId: number) {
  const { data } = await api.get<{ tracks: TimelineTrack[] | null }>(
    `/api/videos/${videoId}/timeline`
  )
  return data.tracks
}

export async function saveTimeline(
  videoId: number,
  operations: TimelineOperations
) {
  const { data } = await api.put<{ tracks: TimelineTrack[] }>(
    `/api/videos/${videoId}/timeline`,
    operations
  )
  return data.tracks
}

export async function renderTimeline(videoId: number) {
  const { data } = await api.post<{ rendered_path: string }>(
    `/api/videos/${videoId}/timeline/render`
  )
  return data
}

/** A timeline can anchor to a crawled video OR a multi-scene project built with AI
 * (Phase 14/16). Both share the editor so it is wrapped as a single type instead of
 * passing a boolean flag `isProject` down everywhere. */
export type TimelineSubject =
  | { type: 'video'; id: number }
  | { type: 'project'; id: number }

function subjectBase(subject: TimelineSubject): string {
  return subject.type === 'video'
    ? `/api/videos/${subject.id}`
    : `/api/projects/${subject.id}`
}

export async function getSubjectTimeline(subject: TimelineSubject) {
  const { data } = await api.get<{ tracks: TimelineTrack[] | null }>(
    `${subjectBase(subject)}/timeline`
  )
  return data.tracks
}

export async function saveSubjectTimeline(
  subject: TimelineSubject,
  operations: TimelineOperations
) {
  const { data } = await api.put<{ tracks: TimelineTrack[] }>(
    `${subjectBase(subject)}/timeline`,
    operations
  )
  return data.tracks
}

export async function renderSubjectTimeline(subject: TimelineSubject) {
  const { data } = await api.post<{ rendered_path: string }>(
    `${subjectBase(subject)}/timeline/render`
  )
  return data
}

/** Timeline suggestion for a project: built straight from the scenes that have clips on the canvas —
 * the equivalent of `buildSuggestionFromPipeline` for crawled videos. */
export async function getProjectTimelineSuggestion(projectId: number) {
  const { data } = await api.get<{ tracks: TimelineTrack[] }>(
    `/api/projects/${projectId}/timeline/suggestion`
  )
  return data.tracks
}

export async function getWaveform(videoId: number, variant: string = 'dubbed') {
  const { data } = await api.get<{ peaks: number[] }>(
    `/api/videos/${videoId}/waveform`,
    {
      params: { variant },
    }
  )
  return data.peaks
}

// --- Phase 11: short TikTok/Shorts clips ---
export interface ClipCandidate {
  start: number
  end: number
  text: string
  score: number
}

export interface CropBox {
  x: number
  y: number
  width: number
  height: number
}

export async function getClipCandidates(videoId: number) {
  const { data } = await api.get<ClipCandidate[]>(
    `/api/videos/${videoId}/clip-candidates`
  )
  return data
}

export async function createClip(
  videoId: number,
  payload: { start: number; end: number; crop?: CropBox; cta_text?: string }
) {
  const { data } = await api.post<{ output_path: string }>(
    `/api/videos/${videoId}/clips`,
    payload
  )
  return data
}

// --- Phase 14: AI Studio (generate images/video with AI) ---

export type GeneratedAssetType = 'image' | 'video'

export interface CharacterReferenceRead {
  id: number
  name: string
  description: string | null
  image_count: number
  created_at: string
}

export interface GeneratedAssetRead {
  id: number
  type: GeneratedAssetType
  prompt: string
  provider: string
  model: string
  duration_seconds: number | null
  cost_estimate_usd: number
  source_character_ref_id: number | null
  source_keyframe_asset_id: number | null
  output_prefix: string | null
  sequence_no: number | null
  created_at: string
}

export interface GenerationResponse {
  asset: GeneratedAssetRead
  /** true = return the previously generated result, no API call and no cost. */
  from_cache: boolean
}

export interface CostEstimate {
  estimated_cost_usd: number
  model: string
  warning: string | null
}

export interface BudgetStatus {
  spent_this_month_usd: number
  monthly_budget_usd: number
  remaining_usd: number
}

export interface GenerationMode {
  mode: 'fake' | 'real'
  is_fake: boolean
}

export async function getGenerationMode() {
  const { data } = await api.get<GenerationMode>('/api/ai-studio/mode')
  return data
}

export async function getGenerationBudget() {
  const { data } = await api.get<BudgetStatus>('/api/ai-studio/budget')
  return data
}

export async function getCharacterReferences() {
  const { data } = await api.get<CharacterReferenceRead[]>(
    '/api/ai-studio/character-references'
  )
  return data
}

export async function createCharacterReference(
  name: string,
  images: File[],
  description?: string
) {
  const form = new FormData()
  form.append('name', name)
  if (description) form.append('description', description)
  images.forEach((image) => form.append('images', image))
  const { data } = await api.post<CharacterReferenceRead>(
    '/api/ai-studio/character-references',
    form
  )
  return data
}

export async function deleteCharacterReference(referenceId: number) {
  await api.delete(`/api/ai-studio/character-references/${referenceId}`)
}

export async function getGeneratedAssets(assetType?: GeneratedAssetType) {
  const { data } = await api.get<GeneratedAssetRead[]>(
    '/api/ai-studio/assets',
    {
      params: assetType ? { asset_type: assetType } : undefined,
    }
  )
  return data
}

/** Preview URL of the keyframe image / video clip playback — used in <img>/<video>. */
export function generatedAssetFileUrl(assetId: number) {
  return `${API_BASE_URL}/api/ai-studio/assets/${assetId}/file`
}

export async function getGenerationCostEstimate(params: {
  asset_type: GeneratedAssetType
  model?: string
  duration_seconds?: number
  count?: number
}) {
  const { data } = await api.get<CostEstimate>('/api/ai-studio/cost-estimate', {
    params,
  })
  return data
}

export async function generateKeyframe(payload: {
  prompt: string
  model?: string
  character_ref_id?: number | null
  output_prefix?: string | null
  confirm_expensive?: boolean
}) {
  const { data } = await api.post<GenerationResponse>(
    '/api/ai-studio/generate/keyframe',
    payload
  )
  return data
}

export async function generateVideoClip(payload: {
  prompt: string
  keyframe_start_asset_id: number
  keyframe_end_asset_id?: number | null
  model?: string
  duration_seconds?: number
  output_prefix?: string | null
  confirm_expensive?: boolean
}) {
  const { data } = await api.post<GenerationResponse>(
    '/api/ai-studio/generate/video-clip',
    payload
  )
  return data
}

// --- Background content generation (Phase 14) ---
// A real provider takes 1-5 minutes per clip. The synchronous version above is kept for MCP/scripts
// (an agent calling sequentially is simpler just waiting), while the UI uses this async version so
// it can leave the page and come back and still see the result.

export interface GenerationJob {
  id: string
  kind: 'keyframe' | 'clip'
  label: string
  status: 'running' | 'done' | 'failed'
  asset_id: number | null
  file_path: string | null
  cost_usd: number
  from_cache: boolean
  error: string | null
  created_at: string
  finished_at: string | null
}

export async function generateKeyframeAsync(payload: {
  prompt: string
  model?: string
  character_ref_id?: number | null
  output_prefix?: string | null
  confirm_expensive?: boolean
}) {
  const { data } = await api.post<GenerationJob>(
    '/api/ai-studio/generate/keyframe/async',
    payload
  )
  return data
}

export async function generateVideoClipAsync(payload: {
  prompt: string
  keyframe_start_asset_id: number
  keyframe_end_asset_id?: number | null
  model?: string
  duration_seconds?: number
  output_prefix?: string | null
  confirm_expensive?: boolean
}) {
  const { data } = await api.post<GenerationJob>(
    '/api/ai-studio/generate/video-clip/async',
    payload
  )
  return data
}

export async function getGenerationJob(jobId: string) {
  const { data } = await api.get<GenerationJob>(
    `/api/ai-studio/generate/jobs/${jobId}`
  )
  return data
}

export async function listGenerationJobs() {
  const { data } = await api.get<GenerationJob[]>(
    '/api/ai-studio/generate/jobs'
  )
  return data
}

/** Wait for a job to finish. Throws when the job fails so `useMutation` goes into the
 * `onError` branch like the earlier synchronous call — the caller need not change how it handles it. */
export async function waitForGenerationJob(
  jobId: string,
  { intervalMs = 1500 }: { intervalMs?: number } = {}
): Promise<GenerationJob> {
  for (;;) {
    const job = await getGenerationJob(jobId)
    if (job.status === 'done') return job
    if (job.status === 'failed') {
      throw new Error(job.error ?? 'Sinh nội dung thất bại')
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}

/** Put a generated clip/image into the shared file library for assembly in the Timeline Editor. */
export async function exportGeneratedAssetToLibrary(assetId: number) {
  const { data } = await api.post<{
    asset_id: string
    name: string
    kind: string
  }>(`/api/ai-studio/assets/${assetId}/export-to-library`)
  return data
}

export async function generateKenBurnsClip(payload: {
  keyframe_asset_id: number
  duration_seconds?: number
  motion?: string
  output_prefix?: string | null
}) {
  const { data } = await api.post<GenerationResponse>(
    '/api/ai-studio/generate/ken-burns',
    payload
  )
  return data
}

// --- Phase 14: MCP access token (for external agents like Claude Code) ---

export interface McpTokenRead {
  id: number
  name: string
  scopes: string[]
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface McpTokenCreated {
  token: McpTokenRead
  /** Only present in the creation response — cannot be retrieved afterwards. */
  plain_token: string
  mcp_config: Record<string, unknown>
  warning: string
}

export async function getMcpScopes() {
  const { data } = await api.get<{ scopes: string[] }>('/api/mcp-tokens/scopes')
  return data.scopes
}

export async function getMcpTokens() {
  const { data } = await api.get<McpTokenRead[]>('/api/mcp-tokens')
  return data
}

export async function createMcpToken(name: string, scopes: string[]) {
  const { data } = await api.post<McpTokenCreated>('/api/mcp-tokens', {
    name,
    scopes,
  })
  return data
}

export async function revokeMcpToken(tokenId: number) {
  await api.delete(`/api/mcp-tokens/${tokenId}`)
}

// --- Phase 16: multi-scene projects (node-canvas) ---

export type SceneStatus = 'draft' | 'keyframe_ready' | 'clip_ready' | 'failed'

export interface SceneRead {
  id: number
  project_id: number
  order_index: number
  prompt: string
  keyframe_asset_id: number | null
  clip_asset_id: number | null
  duration_seconds: number
  /** Effect of the edge ENTERING this scene — the first scene always ignores it. */
  transition_in: string
  transition_duration: number
  /** Frame chaining: use the last frame of the previous scene's clip as the opening keyframe of this scene. */
  chain_from_previous: boolean
  use_ken_burns: boolean
  ken_burns_motion: string
  canvas_x: number
  canvas_y: number
  status: SceneStatus
  error: string | null
}

export interface ProjectRead {
  id: number
  title: string
  output_prefix: string
  rendered_path: string | null
  canvas_viewport: Record<string, number> | null
  created_at: string
  updated_at: string
}

export interface ProjectDetail extends ProjectRead {
  scenes: SceneRead[]
  is_rendering: boolean
}

export async function getProjects() {
  const { data } = await api.get<ProjectRead[]>('/api/projects')
  return data
}

export async function getProject(projectId: number) {
  const { data } = await api.get<ProjectDetail>(`/api/projects/${projectId}`)
  return data
}

export async function createProject(title: string, scenePrompts?: string[]) {
  const { data } = await api.post<ProjectDetail>('/api/projects', {
    title,
    scene_prompts: scenePrompts ?? null,
  })
  return data
}

export async function deleteProject(projectId: number) {
  await api.delete(`/api/projects/${projectId}`)
}

export async function addScene(
  projectId: number,
  payload: { prompt?: string; after_scene_id?: number | null } = {}
) {
  const { data } = await api.post<SceneRead>(
    `/api/projects/${projectId}/scenes`,
    {
      prompt: payload.prompt ?? '',
      after_scene_id: payload.after_scene_id ?? null,
    }
  )
  return data
}

export async function updateScene(
  sceneId: number,
  patch: {
    prompt?: string
    duration_seconds?: number
    transition_in?: string
    transition_duration?: number
    chain_from_previous?: boolean
    use_ken_burns?: boolean
    ken_burns_motion?: string
  }
) {
  const { data } = await api.patch<SceneRead>(
    `/api/projects/scenes/${sceneId}`,
    patch
  )
  return data
}

export async function deleteScene(sceneId: number) {
  await api.delete(`/api/projects/scenes/${sceneId}`)
}

export async function reorderScenes(projectId: number, sceneIds: number[]) {
  const { data } = await api.post<SceneRead[]>(
    `/api/projects/${projectId}/reorder`,
    {
      scene_ids: sceneIds,
    }
  )
  return data
}

export async function saveProjectCanvas(
  projectId: number,
  positions: { scene_id: number; x: number; y: number }[],
  viewport?: Record<string, number> | null
) {
  await api.put(`/api/projects/${projectId}/canvas`, {
    positions,
    viewport: viewport ?? null,
  })
}

export async function generateProjectScene(
  sceneId: number,
  confirmExpensive = false
) {
  const { data } = await api.post<SceneRead>(
    `/api/projects/scenes/${sceneId}/generate`,
    null,
    { params: { confirm_expensive: confirmExpensive } }
  )
  return data
}

export interface ProjectCostEstimate {
  total_scenes: number
  /** Only scenes without a clip cost money — already-generated scenes are reused. */
  pending_scenes: number
  /** The scene uses a still image + camera motion (ffmpeg) — free. */
  free_scenes: number
  image_cost_usd: number
  video_cost_usd: number
  total_cost_usd: number
  warning: string | null
}

export async function getProjectCostEstimate(projectId: number) {
  const { data } = await api.get<ProjectCostEstimate>(
    `/api/projects/${projectId}/cost-estimate`
  )
  return data
}

export async function startProjectRender(projectId: number) {
  const { data } = await api.post<{ project_id: number; message: string }>(
    `/api/projects/${projectId}/render`
  )
  return data
}

/** Put the built video into the shared library to open in the Timeline Editor. */
export async function exportProjectToLibrary(projectId: number) {
  const { data } = await api.post<{
    asset_id: string
    name: string
    kind: string
  }>(`/api/projects/${projectId}/export-to-library`)
  return data
}

/** URL of the built video — used directly in <video>. */
export function projectOutputUrl(projectId: number) {
  return `${API_BASE_URL}/api/projects/${projectId}/output`
}

export async function getYoutubeStatus() {
  const { data } = await api.get<{ configured: boolean }>(
    '/api/trending/youtube/status'
  )
  return data
}

export async function getYoutubeCategories(regionCode = 'VN') {
  const { data } = await api.get<YoutubeCategory[]>(
    '/api/trending/youtube/categories',
    { params: { region_code: regionCode } }
  )
  return data
}

export async function getYoutubeTrending(
  regionCode: string,
  categoryId: string | null,
  pageToken: string | null
) {
  const { data } = await api.get<YoutubeTrendingPage>(
    '/api/trending/youtube/trending',
    {
      params: {
        region_code: regionCode,
        category_id: categoryId ?? undefined,
        page_token: pageToken ?? undefined,
      },
    }
  )
  return data
}

export async function getTopics() {
  const { data } = await api.get<Topic[]>('/api/topics')
  return data
}

export async function createTopic(payload: {
  name: string
  query?: string
  note?: string
}) {
  const { data } = await api.post<Topic>('/api/topics', payload)
  return data
}

export async function deleteTopic(topicId: number) {
  await api.delete(`/api/topics/${topicId}`)
}

export async function computeTopicScore(topicId: number) {
  const { data } = await api.post<Topic>(`/api/topics/${topicId}/score`)
  return data
}

/** User settings persisted across restarts — Phase 21 (download thread count per
 * video) + Phase 20 (number of videos downloading at once). The first page of the tool with
 * settings that are really saved from the UI (the other pages in /settings are still demos of the
 * shadcn-admin template). */
export interface AppSettings {
  download_connections: number
  download_max_videos: number
  /** Speaker separation (Phase 19) — off by default. */
  speaker_diarization_enabled: boolean
}

export async function getAppSettings() {
  const { data } = await api.get<AppSettings>('/api/settings')
  return data
}

export async function updateAppSettings(patch: Partial<AppSettings>) {
  const { data } = await api.put<AppSettings>('/api/settings', patch)
  return data
}

export type ImportedVideo = {
  id: number
  title: string
  status: string
  duration_seconds: number | null
  cover_url: string | null
}

/** Import 1 video file already on the machine. `onProgress` receives 0-100 by the bytes sent. */
export async function importLocalVideo(
  file: File,
  onProgress?: (percent: number) => void
) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<ImportedVideo>('/api/videos/import', form, {
    // A large file can take many minutes — do not let axios cut it off with the default timeout.
    timeout: 0,
    onUploadProgress: (e) => {
      if (e.total) onProgress?.((e.loaded / e.total) * 100)
    },
  })
  return data
}

export type SystemLogs = { path: string; exists: boolean; lines: string[] }

export async function getSystemLogs(lines = 500) {
  const { data } = await api.get<SystemLogs>('/api/system/logs', {
    params: { lines },
  })
  return data
}

export type PackInfo = {
  id: 'ffmpeg' | 'ai'
  label: string
  approx_size_mb: number
  installed: boolean
  state: 'idle' | 'downloading' | 'extracting' | 'done' | 'error'
  downloaded: number
  total: number | null
  error: string | null
}

export async function getPacks() {
  const { data } = await api.get<PackInfo[]>('/api/system/packs')
  return data
}

export async function installPack(id: PackInfo['id']) {
  const { data } = await api.post<PackInfo[]>(`/api/system/packs/${id}/install`)
  return data
}
