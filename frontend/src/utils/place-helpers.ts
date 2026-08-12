/**
 * P2-4-A: 从 pages/index/index.tsx 抽出的纯函数 helpers 集合。
 *
 * 这些函数无组件状态依赖、无 React hook，纯 input → output。
 * 抽出来后:
 *   - index.tsx 体积砍小
 *   - 单测可以独立写
 *   - 其他 component 可以复用（PlaceCard / MapCanvas 等）
 */
import Taro from '@tarojs/taro'
import type { Place, SourceItem, TimeRange } from '../types'

// —— 常量 + 类型 —— //

export const DEFAULT_CENTER = { lat: 30.2741, lon: 120.1551 }

export type FacilityFilterKey = 'all' | 'toilet' | 'water' | 'electricity'

export const FACILITY_FILTERS: Array<{ key: FacilityFilterKey; label: string; hint: string }> = [
  { key: 'all', label: '全', hint: '全部设施' },
  { key: 'toilet', label: '卫', hint: '有厕所' },
  { key: 'water', label: '水', hint: '有水源' },
  { key: 'electricity', label: '电', hint: '可接电' },
]

export const TIME_RANGES: Array<{ key: TimeRange; label: string; days?: number }> = [
  { key: '365d', label: '近一年', days: 365 },
  { key: '7d', label: '近1周', days: 7 },
  { key: '30d', label: '近1个月', days: 30 },
  { key: '90d', label: '近3个月', days: 90 },
  { key: '180d', label: '近6个月', days: 180 },
  { key: 'all', label: '全部', days: undefined },
]

// T8 D8-3 B：localStorage 求证进度打点 key
export const VIEWED_SOURCES_KEY = 'wd_viewed_sources_v1'

// 平台识别 / icon 元数据
export type PlatformKey = 'xhs' | 'bilibili' | 'douyin' | 'mafengwo' | 'zhihu' | 'weibo' | 'gov' | 'other'

export const PLATFORM_META: Record<PlatformKey, { label: string; bg: string; char: string }> = {
  xhs:      { label: '小红书',   bg: '#FF2442', char: '红' },
  bilibili: { label: 'B 站',    bg: '#00A1D6', char: 'B' },
  douyin:   { label: '抖音',    bg: '#161823', char: '♪' },
  mafengwo: { label: '马蜂窝',   bg: '#FFC600', char: '蜂' },
  zhihu:    { label: '知乎',    bg: '#0084FF', char: '知' },
  weibo:    { label: '微博',    bg: '#E6162D', char: '微' },
  gov:      { label: '政府公告', bg: '#C71D24', char: '★' },
  other:    { label: '网页来源', bg: '#6B7280', char: '源' },
}

// —— 日期 / 距离格式 —— //

export function formatDate(value?: string | null) {
  if (!value) return '日期未知'
  return value.slice(0, 10)
}

export function formatDistance(value?: number | null) {
  if (typeof value !== 'number') return '附近'
  if (value < 1) return `${Math.round(value * 1000)}m`
  return `${value.toFixed(value >= 10 ? 0 : 1)}km`
}

export function extractDateFromText(value?: string | null) {
  if (!value) return null
  const text = String(value)
  const match = text.match(/(20\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?/)
  if (!match) return null
  const year = match[1]
  const month = match[2].padStart(2, '0')
  const day = (match[3] || '1').padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function latestDateOf(place: Place) {
  const explicit = place.latest_source_date || place.last_verified_at
  if (explicit) return explicit
  const sourceDates = factSources(place.sources)
    .map((source) => sourceDate(source) || extractDateFromText(`${source.title || ''} ${source.snippet || ''}`))
    .filter(Boolean) as string[]
  if (sourceDates.length) {
    sourceDates.sort()
    return sourceDates[sourceDates.length - 1] || null
  }
  return extractDateFromText(`${place.ai_summary || ''} ${place.positive_summary || ''} ${place.negative_summary || ''} ${place.source_summary || ''}`)
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const radius = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return Math.round(radius * 2 * Math.asin(Math.sqrt(a)) * 10) / 10
}

// —— 时间 / 设施筛选 —— //

export function inTimeRange(place: Place, range: TimeRange) {
  // 时间筛选语义：只剔除"明确过时"的点位；日期未知的默认保留（避免误杀）
  const config = TIME_RANGES.find((item) => item.key === range)
  if (!config?.days) return true
  const dateText = latestDateOf(place)
  if (!dateText) return true  // 日期未知 → 默认显示，由用户判断
  const timestamp = new Date(dateText).getTime()
  if (Number.isNaN(timestamp)) return true  // 解析失败 → 同样默认显示
  return Date.now() - timestamp <= config.days * 24 * 60 * 60 * 1000
}

export function statusText(value?: string | null) {
  if (!value || value === 'unknown' || value === '未知' || value.includes('未核验') || value.includes('未提到')) return '来源未提到'
  return value
}

export function hasFacilitySignal(value?: string | null) {
  const text = statusText(value)
  if (text === '来源未提到') return false
  return !['未知', '无', '没有', '不可', '不支持'].some((term) => text.includes(term))
}

export function matchesFacility(place: Place, filter: FacilityFilterKey) {
  if (filter === 'all') return true
  if (filter === 'toilet') return hasFacilitySignal(place.toilet_status)
  if (filter === 'water') return hasFacilitySignal(place.water_status)
  if (filter === 'electricity') return hasFacilitySignal(place.electricity_status)
  return true
}

// —— Place 性质判断 —— //

export function isAiCandidate(place: Place) {
  return place.data_origin === 'ai_search' || place.status === 'pending_review'
}

export function isPersistedPlace(place: Place) {
  return Boolean(place.id && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(place.id))
}

export function sourceKindText(place: Place) {
  return isAiCandidate(place) ? 'AI提炼' : '公开来源'
}

export function sourceTimeText(place: Place) {
  if (place.source_time_status === 'known') return '信源日期已知'
  if (place.source_time_status === 'mixed') return '部分信源有日期'
  return latestDateOf(place) ? '信源日期已知' : '信源日期未知'
}

// —— Source 工具 —— //

export function sourceUrl(source: SourceItem) {
  return source.source_url || source.url || ''
}

export function sourceDate(source: SourceItem) {
  return source.source_time || source.updated_at || source.published_at || null
}

export function isMapOnlySource(source: SourceItem) {
  const domain = (source.domain || '').toLowerCase()
  const url = sourceUrl(source).toLowerCase()
  const text = `${source.title || ''} ${source.snippet || ''}`
  return (
    source.source_type === '地图数据' ||
    domain.includes('openstreetmap') ||
    url.includes('openstreetmap.org') ||
    /OpenStreetMap|\bOSM\b|冷启动/i.test(text)
  )
}

export function factSources(sources?: SourceItem[]) {
  return (sources || []).filter((source) => !isMapOnlySource(source))
}

// —— 内部标签清洗 —— //

/**
 * AI 回答正文的"裸链接噪声"清洗（仅展示层使用，不改动原始数据）。
 *
 * AI 联网回答常按抽取模板逐条输出"…，来源链接：http://xxx"，裸 URL 又长又不可点，
 * 与下方可点击的信源 chip 完全重复。这里剥掉：
 *  1. "来源链接：<URL>" 整段（含前导顿号/逗号；URL 可能是 http(s) 或为空/无）
 *  2. 残留的孤立裸 URL（SSE 打字机流式期间可能先到一半 URL，也能被兜住）
 *  3. 清洗后遗留的空标点尾巴（"，。"→"。"）
 */
export function stripAnswerLinkNoise(value?: string | null) {
  if (!value) return ''
  return value
    .replace(/[，,、]?\s*来源链接[:：]\s*(https?:\/\/\S*|无|未提供)?/g, '')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[，,]\s*([。；])/g, '$1')
    .replace(/[ \t]+\n/g, '\n')
    .trim()
}

export function cleanInternalText(value?: string | null) {
  if (!value) return ''
  return value
    .replace(/OSM 冷启动 POI。扩展 POI 默认低可信，不能直接视为可露营\/可过夜。/g, '地图导入线索，需查看公开来源。')
    .replace(/OSM冷启动点位，需AI或用户核验/g, '地图导入线索，需查看公开来源。')
    .replace(/人工冷启动种子点，仅作 demo 演示，不能视为可露营\/可过夜结论。/g, '人工导入线索，需查看公开来源。')
    .replace(/人工种子点，需 AI 或用户核验/g, '人工导入线索，需查看公开来源。')
    .replace(/OpenStreetMap[:：]?/gi, '')
    .replace(/\bOSM\b\s*/g, '')
    .replace(/冷启动/g, '导入')
    .replace(/来源待核验/g, '')
    .replace(/待核验/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

export function cleanRiskTags(tags?: string[]) {
  return (tags || [])
    .map(cleanInternalText)
    .filter((tag) => tag && !/OpenStreetMap|\bOSM\b|冷启动|可信|信息不足|来源待确认/i.test(tag))
}

// —— Place 展示属性 —— //

export function displaySourceCount(place: Place) {
  // 注意：空数组 [] 在 JS 是 truthy，旧逻辑会让 sources=[] 的点位被判 0 源 → 过滤掉
  // 修复：只有当 sources 是非空数组时才用它的长度；否则回落到后端给的 source_count
  if (Array.isArray(place.sources) && place.sources.length > 0) {
    return factSources(place.sources).length
  }
  return Number(place.source_count || 0)
}

export function displaySummary(place: Place) {
  return cleanInternalText(place.ai_summary || place.positive_summary || place.source_summary) || '暂无来源摘要'
}

export function vehicleText(place: Place) {
  const values = place.vehicle_fit || []
  if (!values.length) return '来源未提到'
  if (values.length === 3 && values.includes('轿车') && values.includes('SUV') && values.includes('床车')) return '来源未提到'
  return values.join(' / ')
}

export function matchesCategory(place: Place, nextCategory: string) {
  if (!nextCategory || nextCategory === '全部') return true
  const type = place.type || ''
  const text = `${place.name || ''}${place.type || ''}${place.address || ''}${place.ai_summary || ''}${place.source_summary || ''}`
  if (nextCategory === '窝窝' || nextCategory === '驻车点') return ['驻车', '停车', '床车', '房车'].some((term) => type.includes(term) || text.includes(term))
  if (nextCategory === '营地') return ['营地', 'camp_site', 'caravan_site', '商业营地', '景区露营区'].some((term) => type.includes(term) || text.includes(term))
  if (nextCategory === '野外露营') return ['野外', '公园', '水域', '沙滩', '草坪'].some((term) => type.includes(term) || text.includes(term))
  if (nextCategory === '服务区') return type.includes('服务区') || text.includes('服务区')
  if (nextCategory === '美食') return ['餐', '饭', '食', '美食', '服务区'].some((term) => text.includes(term))
  if (nextCategory === '景点') return ['景区', '景点', '公园', '湿地', '湖', '山', '水域', '沙滩'].some((term) => text.includes(term))
  if (nextCategory === '兴趣') return ['钓', '游泳', '温泉', '观景', '露营', '营地', '户外'].some((term) => text.includes(term))
  return true
}

export function normalizeAiSpot(place: Place): Place {
  const sources = factSources(place.sources)
  return {
    ...place,
    id: place.id || `ai-${place.name}-${place.latitude}-${place.longitude}`,
    data_origin: place.data_origin || 'ai_search',
    status: place.status || 'pending_review',
    distance_km: place.distance_km ?? haversineKm(DEFAULT_CENTER.lat, DEFAULT_CENTER.lon, place.latitude, place.longitude),
    sources,
    source_count: place.source_count || sources.length || 0,
    risk_tags: cleanRiskTags(place.risk_tags),
    ai_summary: cleanInternalText(place.ai_summary),
    positive_summary: cleanInternalText(place.positive_summary),
    negative_summary: cleanInternalText(place.negative_summary),
    source_summary: cleanInternalText(place.source_summary),
  }
}

export function sortPlaces(items: Place[]) {
  return [...items].sort((a, b) => {
    const sourceDelta = displaySourceCount(b) - displaySourceCount(a)
    if (sourceDelta) return sourceDelta
    return (a.distance_km ?? 999999) - (b.distance_km ?? 999999)
  })
}

// —— 外部副作用（Taro / 浏览器 API）—— //

export function openExternalUrl(url: string) {
  if (!url) return
  if (process.env.TARO_ENV === 'h5' && typeof window !== 'undefined') {
    window.open(url, '_blank')
    return
  }
  // 微信小程序平台限制：不能直接打开任意外网链接（需业务域名白名单 + HTTPS + 备案）。
  // spec-017 B 方案：先复制到剪贴板（兜底）、再弹二维码 modal 让用户长按 → 微信识别 → 跳浏览器
  // 二维码 modal 由顶层组件（index.tsx）通过 qr-modal-controller 注册回调实现。
  Taro.setClipboardData({ data: url })
  // 延迟 import 避循环依赖（controller 不应依赖 Taro）
  import('./qr-modal-controller').then(({ showQRCodeModal }) => {
    const shown = showQRCodeModal(url)
    if (!shown) {
      // controller 未注册 → 降级到 toast 提示
      Taro.showToast({
        title: '链接已复制，请粘贴到浏览器打开',
        icon: 'none',
        duration: 2500,
      })
    }
  })
}

export function placeKey(place: Place) {
  return place.id || `${place.name}-${place.latitude}-${place.longitude}`
}

// —— 平台识别 —— //

export function detectPlatform(domain?: string | null): PlatformKey {
  const d = (domain || '').toLowerCase()
  if (!d) return 'other'
  if (d.includes('xiaohongshu') || d.includes('xhslink')) return 'xhs'
  if (d.includes('bilibili') || d.includes('b23.tv')) return 'bilibili'
  if (d.includes('douyin') || d.includes('iesdouyin')) return 'douyin'
  if (d.includes('mafengwo')) return 'mafengwo'
  if (d.includes('zhihu')) return 'zhihu'
  if (d.includes('weibo')) return 'weibo'
  if (/\.gov\.cn$/.test(d) || d.endsWith('.gov.cn')) return 'gov'
  return 'other'
}

// —— 求证进度存储（spec-010 R5：localStorage → Taro Storage，双端通用）—— //
// Taro.getStorageSync/setStorageSync：H5 编译为 localStorage、小程序编译为 wx.getStorageSync。
// 小程序无 window.localStorage，原写法会报 `localStorage is not defined`。

export function loadViewedSources(): Set<string> {
  try {
    const raw = Taro.getStorageSync(VIEWED_SOURCES_KEY)
    // 首次无历史：getStorageSync 对不存在的 key 返回空字符串 '' → 这里返回空集合而非报错
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    return new Set(Array.isArray(arr) ? arr : [])
  } catch {
    return new Set()
  }
}

export function persistViewedSources(set: Set<string>) {
  try {
    Taro.setStorageSync(VIEWED_SOURCES_KEY, JSON.stringify(Array.from(set)))
  } catch {
    // 容忍 quota 满
  }
}
