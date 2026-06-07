export type Recommendation = 'recommend' | 'caution' | 'not_recommend'

export interface SourceItem {
  id?: string
  source_type?: string
  source_url?: string
  url?: string
  domain?: string
  title?: string
  snippet?: string
  source_time?: string | null
  published_at?: string | null
  updated_at?: string | null
  reliability_score?: number
}

export interface Place {
  id?: string
  name: string
  type: string
  latitude: number
  longitude: number
  address?: string | null
  city?: string | null
  district?: string | null
  province?: string
  location_confidence?: 'high' | 'medium' | 'low' | 'pending'
  geo_source?: string | null
  ai_rating?: number | null
  credibility_score: number
  recommendation: Recommendation
  source_count: number
  price_clues?: string[]
  overnight_clues?: string[]
  toilet_status?: string | null
  water_status?: string | null
  electricity_status?: string | null
  height_limit?: string | null
  vehicle_fit?: string[]
  risk_tags?: string[]
  ai_summary?: string | null
  positive_summary?: string | null
  negative_summary?: string | null
  source_summary?: string | null
  last_verified_at?: string | null
  latest_source_date?: string | null
  source_time_status?: 'known' | 'unknown' | 'mixed'
  data_origin?: string | null
  status?: string
  updated_at?: string
  distance_km?: number | null
  sources?: SourceItem[]
  feedbacks?: unknown[]
}

export interface PlacesSearchMetadata {
  // 始终有的字段（向后兼容）
  lat: number | null
  lon: number | null
  radius_km: number
  // spec 001-fix-source-geo-filter：地理意图识别结果
  detected_place?: string | null
  search_center?: { lat: number; lon: number } | null
  geocoder?: 'local' | 'amap' | null
}

export interface PlacesResponse {
  total: number
  places: Place[]
  search_metadata?: PlacesSearchMetadata
}

export type WarningCode =
  | 'network_error'
  | 'empty_answer'
  | 'no_traceable_sources'
  | 'extract_timeout'
  | 'unrecognized_location'  // spec-017: 字典 + amap 都识别不到地名 → 明确报错（不 fallback 杭州）

export interface AISearchMetrics {
  cache_hit?: boolean
  model_id?: string | null
  elapsed_seconds?: {
    search?: number | null
    extract?: number | null
    total?: number | null
  }
  tokens?: {
    input?: number | null
    output?: number | null
    search_input?: number | null
    search_output?: number | null
    extract_input?: number | null
    extract_output?: number | null
  }
  cost_cny?: number | null
}

export interface AISearchResponse {
  answer?: {
    text?: string
    sources?: SourceItem[]
  }
  spots?: Place[]
  unmapped_candidates?: Array<{
    name: string
    reason: string
    latest_source_date?: string | null
    source_time_status?: 'known' | 'unknown' | 'mixed'
    sources?: SourceItem[]
  }>
  warning?: string | null
  warning_code?: WarningCode | string | null
  provider?: Record<string, string>
  cache?: { hit?: boolean }
  metrics?: AISearchMetrics
  // 7.5-D：search 完后 extract 改后台跑，complete 时这两个字段告诉前端"还要 poll"
  extract_pending?: boolean
  extract_cache_key?: string
}

/**
 * 7.5-D 后台 extract 任务的 polling 响应。
 * GET /api/v1/search/extract-result/{cache_key}
 */
export interface ExtractResultResponse {
  ready: boolean
  // ready=true 时附带完整 AISearchResponse 内容
  spots?: Place[]
  unmapped_candidates?: AISearchResponse['unmapped_candidates']
  answer?: AISearchResponse['answer']
  sources?: SourceItem[]
  warning?: string | null
  warning_code?: WarningCode | string | null
  provider?: Record<string, string>
  metrics?: AISearchMetrics
  extract_timeout?: boolean
}

export type TimeRange = 'all' | '365d' | '7d' | '30d' | '90d' | '180d'

/**
 * SSE 流式搜索事件（对应后端 POST /api/v1/search/stream 推送的 event 类型）。
 * 7.5-A 提供 search_start / search_done / extract_start / extract_done / complete / error。
 * 7.5-C 新增 web_search_* / text_delta / citation 增量事件。
 */
export type SSEEvent =
  | {
      type: 'search_start'
      data: {
        query: string
        limit: number
        search_center?: { lat: number; lon: number } | null
        detected_place?: string | null
      }
    }
  | { type: 'web_search_in_progress'; data: Record<string, never> }
  | { type: 'web_search_searching'; data: Record<string, never> }
  | { type: 'web_search_completed'; data: Record<string, never> }
  | { type: 'text_delta'; data: { delta: string } }
  | {
      type: 'citation'
      data: { url?: string; title?: string; logo_url?: string; [k: string]: unknown }
    }
  | {
      type: 'search_done'
      data: {
        answer?: AISearchResponse['answer']
        sources?: SourceItem[]
        warning?: string | null
        warning_code?: string | null
        elapsed_seconds?: number | null
      }
    }
  | { type: 'extract_start'; data: Record<string, never> }
  | {
      type: 'extract_done'
      data: {
        timeout?: boolean
        spots_count?: number
        unmapped_count?: number
        elapsed_seconds?: number | null
      }
    }
  | {
      // 7.5-D：search_done 后立刻 yield，告诉前端 extract 改后台 + 拿 cache_key 去 poll
      type: 'extract_async_started'
      data: { extract_cache_key: string; poll_interval_ms?: number; poll_endpoint?: string }
    }
  | { type: 'complete'; data: AISearchResponse }
  | { type: 'error'; data: { warning: string; warning_code: string } }
