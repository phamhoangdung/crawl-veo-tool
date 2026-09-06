import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
})

export type Platform = 'bilibili' | 'douyin'

export type VideoStatus =
  | 'queued'
  | 'downloading'
  | 'downloaded'
  | 'separating_audio'
  | 'transcribing'
  | 'translating'
  | 'dubbing'
  | 'muxing'
  | 'done'
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
}

export interface TrendingCategory {
  rid: number
  name: string
}

export interface TrendingVideo {
  bvid: string
  title: string
  author_name: string | null
  play_count: number | null
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
  status: string
  transcript: TranscriptSegment[]
  dubbed_path: string | null
}

export interface ApiKeyRead {
  provider: string
  masked_key: string
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

export async function createCrawlJob(keyword: string, platform: Platform = 'bilibili') {
  const { data } = await api.post<JobWithVideosRead>('/api/jobs', { keyword, platform })
  return data
}

export async function getTrendingCategories() {
  const { data } = await api.get<TrendingCategory[]>('/api/trending/bilibili/categories')
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
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  return `${base}/api/library/${videoId}/download?variant=${variant}`
}

export function getZipDownloadUrl(videoIds: number[], variant: 'dubbed' | 'burned' | 'original') {
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  return `${base}/api/library/download-zip?video_ids=${videoIds.join(',')}&variant=${variant}`
}

export async function getApiKeys() {
  const { data } = await api.get<ApiKeyRead[]>('/api/api-keys')
  return data
}

export async function saveApiKey(provider: string, apiKey: string) {
  const { data } = await api.put<ApiKeyRead>('/api/api-keys', { provider, api_key: apiKey })
  return data
}
