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
