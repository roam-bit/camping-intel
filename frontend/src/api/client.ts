import Taro from '@tarojs/taro'
import type { AISearchResponse, ExtractResultResponse, Place, PlacesResponse, SSEEvent } from '../types'

// 后端地址唯一来源：编译期由 config/index.js 注入的 TARO_APP_API_BASE。
// 不在此写 fallback——避免「源码 + 构建配置各写一份」的漂移（spec-011 US1）。
const API_BASE = process.env.TARO_APP_API_BASE

type RequestOptions = {
  method?: 'GET' | 'POST'
  data?: Record<string, unknown>
  query?: Record<string, string | number | undefined | null>
  timeout?: number
}

function withQuery(path: string, query?: RequestOptions['query']) {
  if (!query) return path
  const params = Object.entries(query)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&')
  return params ? `${path}?${params}` : path
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await Taro.request<T>({
    url: `${API_BASE}${withQuery(path, options.query)}`,
    method: options.method || 'GET',
    data: options.data,
    header: { 'Content-Type': 'application/json' },
    timeout: options.timeout
  })
  if (response.statusCode >= 400) {
    const data = response.data as { detail?: string } | string
    const message = typeof data === 'string' ? data : data?.detail || `请求失败：${response.statusCode}`
    throw new Error(message)
  }
  return response.data
}

export function getPlaces(params: {
  lat?: number
  lon?: number
  radius_km?: number
  category?: string
  min_credibility?: number
  limit?: number
  /** spec 001：搜索词，后端用它识别地理意图决定 search_center */
  q?: string
}) {
  return request<PlacesResponse>('/api/v1/places', { query: params })
}

export function getPlaceDetail(id: string) {
  return request<Place>(`/api/v1/places/${id}`)
}

export function aiSearch(q: string, limit = 12, radiusKm = 80) {
  return request<AISearchResponse>('/api/v1/ai/search', {
    method: 'POST',
    data: { q, limit, radius_km: radiusKm },
    timeout: 10 * 60 * 1000
  })
}

/**
 * 统一搜索入口（V2 召回策略 B）：
 * 后端先按关键词查 DB，命中 ≥ ceil(limit*0.5) 时秒回；不足时再调 AI 联网兜底。
 * 响应额外含 source_breakdown 字段标明 DB / AI 来源比例。
 */
export function unifiedSearch(q: string, limit = 12, radiusKm = 80, lat = 30.2741, lon = 120.1551) {
  return request<AISearchResponse & { source_breakdown?: { db: number; ai: number; threshold: number; strategy: string } }>(
    '/api/v1/search',
    {
      method: 'POST',
      data: { q, limit, radius_km: radiusKm, lat, lon },
      timeout: 10 * 60 * 1000
    }
  )
}

/**
 * 7.5-B: 消费后端 SSE 流式接口 POST /api/v1/search/stream。
 *
 * 由于 Taro.request 不支持 streaming，H5 端走浏览器原生 fetch + ReadableStream。
 * 小程序（非 H5）环境无 fetch/ReadableStream——本函数内部自动降级为非流式
 * unifiedSearch，把结果合成一个 complete 事件经 onEvent 发射。降级对调用方
 * 透明：调用方用同一套写法，无需按平台分支判断（spec-011 US2）。
 *
 * 用法（callback 风格，避免 async generator 在 Taro 编译链路的兼容坑）:
 *
 *   const abort = new AbortController()
 *   await aiSearchStream(
 *     { q: '杭州周边露营', limit: 12 },
 *     (evt) => {
 *       if (evt.type === 'text_delta') typewriter.append(evt.data.delta)
 *       if (evt.type === 'complete') renderSpots(evt.data.spots)
 *     },
 *     { signal: abort.signal },
 *   )
 */
export async function aiSearchStream(
  params: { q: string; limit?: number; radius_km?: number },
  onEvent: (evt: SSEEvent) => void,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  // 小程序（及任何非 H5 环境）无 fetch/ReadableStream：内部降级为非流式 unifiedSearch。
  // unifiedSearch 的响应本身即 AISearchResponse，与流式 complete 事件的 data 同型，
  // 可直接作为 complete 事件透传——调用方的 onEvent 处理逻辑天然能接住（spec-011 US2）。
  if (process.env.TARO_ENV !== 'h5') {
    const result = await unifiedSearch(params.q, params.limit ?? 12, params.radius_km ?? 80)
    onEvent({ type: 'complete', data: result })
    return
  }
  const response = await fetch(`${API_BASE}/api/v1/search/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      q: params.q,
      limit: params.limit ?? 12,
      radius_km: params.radius_km ?? 80,
    }),
    signal: options.signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`SSE 请求失败 ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 协议：每帧以 \n\n 结尾，帧内多行 event:/data: 字段
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const rawFrame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        boundary = buffer.indexOf('\n\n')
        emitFrame(rawFrame, onEvent)
      }
    }
    // 流结束后兜底处理 buffer 里可能残留的一帧（理论上 SSE 协议总以 \n\n 收尾）
    if (buffer.trim()) emitFrame(buffer, onEvent)
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* noop */
    }
  }
}

function emitFrame(rawFrame: string, onEvent: (evt: SSEEvent) => void): void {
  let eventName: string | null = null
  const dataLines: string[] = []
  for (const line of rawFrame.split('\n')) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    // 忽略 comment 行（以 ":" 开头）和其他字段（id: / retry:）
  }
  if (!eventName || dataLines.length === 0) return
  try {
    const data = JSON.parse(dataLines.join('\n'))
    onEvent({ type: eventName, data } as SSEEvent)
  } catch (err) {
    // 解析失败的帧丢弃，避免单个坏帧打断整流
    // eslint-disable-next-line no-console
    console.warn('[aiSearchStream] 解析 SSE 帧失败', { eventName, dataLines, err })
  }
}

/**
 * 7.5-D: 拉取后台 extract 任务结果（用于 search_done 后的 polling）。
 *
 * complete event 的 extract_cache_key 字段就是这里的入参。
 * 返回 ready=false 表示后台还在跑，前端应继续 polling（建议 2s 一次）。
 * 返回 ready=true 表示已完成，spots/unmapped_candidates 可用于补地图 marker / 线索区。
 */
export function getExtractResult(cacheKey: string): Promise<ExtractResultResponse> {
  return request<ExtractResultResponse>(`/api/v1/search/extract-result/${encodeURIComponent(cacheKey)}`)
}

export function submitFeedback(
  id: string,
  data: {
    can_park_now?: string
    can_overnight?: string
    price_status?: string
    toilet_available?: string
    was_warned?: boolean
    vehicle_type?: string
    comment?: string
  }
) {
  return request<{ place: Place }>(`/api/v1/places/${id}/feedback`, { method: 'POST', data })
}

/** 开发者面板：只读获取「当前参数下的联网搜索 prompt」预览（仅 H5 开发者抽屉使用） */
export function getDevPromptPreview(q: string, limit: number) {
  return request<{ prompt: string; limit_effective: number; model: string }>('/api/v1/dev/prompt-preview', {
    query: { q, limit },
  })
}
