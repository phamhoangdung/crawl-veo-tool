import axios from 'axios'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE_URL,
})

export type Platform = 'bilibili' | 'douyin'

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
}

export interface JobWithVideosRead {
  id: number
  platform: Platform
  keyword: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  created_at: string
  videos: VideoRead[]
  translation_failed: boolean
  /** Số video bị lọc vì đã có trong DB, và tổng số tìm được — không có 2 số này
   *  thì "0 video" trông giống hệt "không tìm thấy gì". */
  skipped_existing: number
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
  heat_score: number
}

export interface CategoryHistory {
  rid: number
  name: string
  points: SnapshotPoint[]
}

export type TaskKind = 'download' | 'transcribe' | 'translate' | 'dub' | 'burn'

export interface TaskProgress {
  video_id: number
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
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  translated_text: string
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

/** Tải thêm 1 trang kết quả search vào job đã có (infinite scroll trang Crawl). */
export async function loadMoreJobVideos(jobId: number, page: number) {
  const { data } = await api.post<JobPage>(`/api/jobs/${jobId}/load-more`, null, {
    params: { page },
  })
  return data
}

/** Tạo job tải từ các video người dùng tick chọn ở trang Trending. */
export async function createJobFromSelection(videos: TrendingVideo[]) {
  const { data } = await api.post<JobWithVideosRead>('/api/jobs/from-selection', {
    videos: videos.map((v) => ({
      bvid: v.bvid,
      title: v.title,
      author_name: v.author_name,
      duration_seconds: v.duration_seconds,
      cover_url: v.cover_url,
    })),
  })
  return data
}

export async function getTrendingCategories() {
  const { data } = await api.get<TrendingCategory[]>('/api/trending/bilibili/categories')
  return data
}

export async function refreshCategories() {
  const { data } = await api.post<TrendingCategory[]>(
    '/api/trending/bilibili/categories/refresh'
  )
  return data
}

export async function getFollowedCategories() {
  const { data } = await api.get<number[]>('/api/trending/bilibili/categories/followed')
  return data
}

export async function setFollowedCategories(rids: number[]) {
  const { data } = await api.put<number[]>('/api/trending/bilibili/categories/followed', {
    rids,
  })
  return data
}

export async function getCategoryHistory(rids: number[], days = 30) {
  const { data } = await api.get<CategoryHistory[]>('/api/trending/bilibili/history', {
    params: { rids: rids.join(','), days },
  })
  return data
}

/** Tiến độ mọi tác vụ đang chạy: tải, tách lời thoại, dịch, lồng tiếng. */
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

/** Mở thư mục chứa file trong Finder/Explorer — chỉ chạy được vì tool ở local. */
export async function revealInFileManager(videoId?: number) {
  const { data } = await api.post<{ opened: string }>('/api/downloads/reveal', null, {
    params: videoId ? { video_id: videoId } : undefined,
  })
  return data
}

/** 1 trang video của category — trang 1 từ bảng xếp hạng, trang sau từ search. */
export async function getCategoryPage(rid: number, page: number) {
  const { data } = await api.get<TrendingPage>('/api/trending/bilibili/category-page', {
    params: { rid, page },
  })
  return data
}

export async function getCategoryStats(rids: number[]) {
  const { data } = await api.get<CategoryStats[]>('/api/trending/bilibili/stats', {
    params: { rids: rids.join(',') },
  })
  return data
}

export async function getTrendingRanking(rid: number) {
  const { data } = await api.get<TrendingVideo[]>('/api/trending/bilibili/ranking', {
    params: { rid },
  })
  return data
}

export async function getVideoDetail(videoId: number) {
  const { data } = await api.get<VideoDetail>(`/api/videos/${videoId}`)
  return data
}

export async function downloadVideo(videoId: number) {
  const { data } = await api.post<VideoDetail>(`/api/videos/${videoId}/download`)
  return data
}

export async function transcribeVideo(videoId: number) {
  const { data } = await api.post<VideoDetail>(`/api/videos/${videoId}/transcribe`)
  return data
}

export async function translateVideo(videoId: number, sourceLang = 'zh', targetLang = 'vi') {
  const { data } = await api.post<VideoDetail>(`/api/videos/${videoId}/translate`, {
    source_lang: sourceLang,
    target_lang: targetLang,
  })
  return data
}

export async function updateTranscript(videoId: number, segments: TranscriptSegment[]) {
  const { data } = await api.put<VideoDetail>(`/api/videos/${videoId}/transcript`, segments)
  return data
}

export async function dubVideo(videoId: number, keepBackground = true) {
  const { data } = await api.post<VideoDetail>(`/api/videos/${videoId}/dub`, null, {
    params: { keep_background: keepBackground },
  })
  return data
}

export async function burnSubtitles(videoId: number) {
  const { data } = await api.post<VideoDetail>(`/api/videos/${videoId}/burn-subtitles`)
  return data
}

export async function getLibrary() {
  const { data } = await api.get<LibraryItem[]>('/api/library')
  return data
}

export function getDownloadUrl(videoId: number, variant: 'dubbed' | 'burned' | 'original') {
  return `${API_BASE_URL}/api/library/${videoId}/download?variant=${variant}`
}

export function getZipDownloadUrl(videoIds: number[], variant: 'dubbed' | 'burned' | 'original') {
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
  const { data } = await api.delete<{ deleted: boolean }>(`/api/files/${videoId}/${variant}`)
  return data
}

export async function deleteVideoFiles(videoId: number) {
  const { data } = await api.delete<{ freed_bytes: number }>(`/api/files/${videoId}`)
  return data
}

export async function cleanupOrphanFiles() {
  const { data } = await api.post<{ freed_bytes: number }>('/api/files/cleanup-orphans')
  return data
}

export async function getApiKeys() {
  const { data } = await api.get<ApiKeyRead[]>('/api/api-keys')
  return data
}

export async function addApiKey(provider: string, apiKey: string, label?: string) {
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

// --- Phase 13: trình chỉnh sửa timeline ---
// Hình dạng "clip" gộp chung field của cả 3 loại track (video/audio/overlay) thay
// vì union type riêng — đơn giản hoá thao tác kéo-thả/patch ở store, khớp với
// schema backend (dict[str, Any] theo track, xem app/schemas/timeline.py).
export interface TimelineClip {
  source?: string
  text?: string
  /** Clip ảnh hiện suốt video thì bỏ trống start/end; các loại khác luôn có. */
  start?: number
  end?: number
  track_start?: number
  volume?: number
  transition_in?: 'cut' | 'fade'
  transition_duration?: number
  x?: number
  y?: number
  font_size?: number
  /** Track ảnh (logo/watermark): bề rộng theo tỉ lệ khung hình [0,1]. */
  width?: number
  /** Track ảnh: độ mờ [0,1] — watermark thường để 0.3-0.6. */
  opacity?: number
}

export interface TimelineTrack {
  type: 'video' | 'audio' | 'overlay' | 'image'
  role?: string
  clips: TimelineClip[]
}

export interface TimelineOperations {
  tracks: TimelineTrack[]
}

// --- Dịch text lẻ cho tooltip (có cache ở backend) ---

export interface TranslateResult {
  translated_text: string
  cached: boolean
}

export async function translateText(text: string, sourceLang = 'zh', targetLang = 'vi') {
  const { data } = await api.post<TranslateResult>('/api/translate', {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
  })
  return data
}

/** Dịch cả trang trong 1 request — 40 request rời rạc sẽ đụng rate limit. */
export async function translateBatch(texts: string[], sourceLang = 'zh', targetLang = 'vi') {
  const { data } = await api.post<{ translations: Record<string, string> }>(
    '/api/translate/batch',
    { texts, source_lang: sourceLang, target_lang: targetLang }
  )
  return data.translations
}

// --- Kho file dùng chung: logo, intro/outro, nhạc nền (Phase 9) ---
// Asset dùng lại cho NHIỀU video nên lưu riêng, không nằm trong thư mục 1 video.

export type AssetKind = 'image' | 'video' | 'audio'

export interface Asset {
  id: string
  name: string
  kind: AssetKind
  /** Đường dẫn tuyệt đối trên máy — đây là thứ đưa vào `source` của clip. */
  path: string
  size: number
}

export async function listAssets(kind?: AssetKind) {
  const { data } = await api.get<Asset[]>('/api/assets', { params: kind ? { kind } : undefined })
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

/** URL xem trước (ảnh logo, nghe thử nhạc nền) — dùng trực tiếp trong <img>/<audio>. */
export function assetFileUrl(assetId: string) {
  return `${API_BASE_URL}/api/assets/${assetId}/file`
}

export interface AudioStems {
  voice: string | null
  background: string | null
  mixed: string | null
}

/** Track audio đã tách rời, để chỉnh âm lượng giọng đọc và nhạc nền riêng. */
export async function getAudioStems(videoId: number) {
  const { data } = await api.get<AudioStems>(`/api/videos/${videoId}/audio-stems`)
  return data
}

export async function getTimeline(videoId: number) {
  const { data } = await api.get<{ tracks: TimelineTrack[] | null }>(
    `/api/videos/${videoId}/timeline`
  )
  return data.tracks
}

export async function saveTimeline(videoId: number, operations: TimelineOperations) {
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

export async function getWaveform(videoId: number, variant: string = 'dubbed') {
  const { data } = await api.get<{ peaks: number[] }>(`/api/videos/${videoId}/waveform`, {
    params: { variant },
  })
  return data.peaks
}

// --- Phase 11: clip ngắn TikTok/Shorts ---
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
  const { data } = await api.get<ClipCandidate[]>(`/api/videos/${videoId}/clip-candidates`)
  return data
}

export async function createClip(
  videoId: number,
  payload: { start: number; end: number; crop?: CropBox; cta_text?: string }
) {
  const { data } = await api.post<{ output_path: string }>(`/api/videos/${videoId}/clips`, payload)
  return data
}
