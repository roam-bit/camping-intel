import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { aiSearchStream, getExtractResult, getPlaceDetail, getPlaces, submitFeedback, unifiedSearch } from '../../api/client'
import type { AISearchResponse, Place, SourceItem, TimeRange } from '../../types'
import { useUserLocation } from '../../hooks/useUserLocation'
import { useViewedSources } from '../../hooks/useViewedSources'
import { usePlaces } from '../../hooks/usePlaces'
// amap utils 已搬入 MapCanvas / PlaceCard / PlaceDetailDrawer 内部，index.tsx 不再直接调用
// P2-4-A：纯函数 helpers / 常量 / 类型抽到 utils/place-helpers.ts
import {
  DEFAULT_CENTER,
  FACILITY_FILTERS,
  TIME_RANGES,
  cleanInternalText,
  cleanRiskTags,
  displaySourceCount,
  displaySummary,
  extractDateFromText,
  factSources,
  formatDate,
  formatDistance,
  hasFacilitySignal,
  haversineKm,
  inTimeRange,
  isAiCandidate,
  isMapOnlySource,
  isPersistedPlace,
  latestDateOf,
  loadViewedSources,
  matchesCategory,
  matchesFacility,
  normalizeAiSpot,
  openExternalUrl,
  persistViewedSources,
  placeKey,
  sortPlaces,
  sourceDate,
  sourceKindText,
  sourceTimeText,
  sourceUrl,
  statusText,
  vehicleText,
} from '../../utils/place-helpers'
import type { FacilityFilterKey } from '../../utils/place-helpers'
import { PlatformIcon } from '../../components/PlatformIcon'
import { EmptyHero } from '../../components/EmptyHero'
import { SearchBar } from '../../components/SearchBar'
import { AnswerPanel } from '../../components/AnswerPanel'
import { PlaceCard } from '../../components/PlaceCard'
import { SourceLeadCard } from '../../components/SourceLeadCard'
import { PlaceDetailDrawer } from '../../components/PlaceDetailDrawer'
import { QRCodeModal } from '../../components/QRCodeModal'
import { registerQRModalShowFn } from '../../utils/qr-modal-controller'
import { AiRiskNotice } from '../../components/AiContentLabels'
import { MapCanvas } from '../../components/MapCanvas'
import './index.css'

// T7 D7-3 A：3 个固定示例 query 芯片

// T7 D7-4 B：搜索完成后出现的结果分类 Tab（基于点位 type 做二次筛选）
const RESULT_TABS: Array<{ key: string; label: string }> = [
  { key: '全部', label: '全部' },
  { key: '营地', label: '营地' },
  { key: '驻车点', label: '驻车点' },
  { key: '野外露营', label: '野外' }
]

export default function IndexPage() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [hasSearched, setHasSearched] = useState(false)
  // 用户主动关闭"启动引导卡"（不挡地图视野）
  const [heroDismissed, setHeroDismissed] = useState(false)
  const [timeRange, setTimeRange] = useState<TimeRange>('365d')
  const [facilityFilter, setFacilityFilter] = useState<FacilityFilterKey>('all')
  const [radiusKm] = useState(80)
  // P2-4-G: places + loadPlaces + loading 抽到 usePlaces hook（声明放下方，等 userCoord/radiusKm 准备好）
  const [aiCandidates, setAiCandidates] = useState<Place[]>([])
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null)
  const [answer, setAnswer] = useState<AISearchResponse['answer'] | null>(null)
  const [unmapped, setUnmapped] = useState<AISearchResponse['unmapped_candidates']>([])
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map')
  // loading state 由 usePlaces 提供（声明在 hook 调用后）
  const [searching, setSearching] = useState(false)
  const [progress, setProgress] = useState('')
  const [warning, setWarning] = useState('')
  const [warningCode, setWarningCode] = useState<string | null>(null)
  const [searchCenter, setSearchCenter] = useState<{ lat: number; lon: number; name?: string | null } | null>(null)
  const [mapError, setMapError] = useState('')
  // spec-017 B 方案：链接二维码 modal（点信源链接弹出、用户长按二维码 → 微信识别 → 跳浏览器）
  const [qrModalUrl, setQrModalUrl] = useState<string | null>(null)
  useEffect(() => {
    registerQRModalShowFn(setQrModalUrl)
    return () => { registerQRModalShowFn(null) }
  }, [])
  // T8 D8-3 B：求证进度打点（localStorage 持久化的已点击信源 URL 集合）
  // P2-4-G: viewedSources state + markSourceViewed 抽到 useViewedSources hook
  const { viewedSources, markSourceViewed } = useViewedSources()
  // 7.5-D：每次搜索递增的序列号，让"过期"的后台 polling 自我丢弃，避免老搜索覆盖新搜索的结果
  const searchSeqRef = useRef(0)
  // P2-5: 用户真实地理位置（H5 端调浏览器 geolocation）；失败/拒绝时 coord 仍是杭州默认
  const { coord: userCoord, status: locationStatus, isFallback: locationFallback } = useUserLocation()
  // P2-4-G: 周边点位 state + 加载封装；onError 走统一 setWarning
  const { places, loading, loadPlaces, searchMetadata } = usePlaces({ userCoord, radiusKm, onError: (msg) => setWarning(msg) })

  // P2-5: 定位完成后给一次性提示 + 真实坐标拿到时重新加载周边 + 地图重 center
  useEffect(() => {
    // spec-013 D2：加载点位与「定位是否成功」解耦——三种终态都 loadPlaces()。
    // 定位失败时 userCoord 已是杭州默认坐标，照样能加载周边点位（不再空白）。
    if (locationStatus === 'denied') {
      Taro.showToast({ title: '未授权位置，使用杭州默认中心', icon: 'none', duration: 2500 })
      loadPlaces()
    } else if (locationStatus === 'error') {
      Taro.showToast({ title: '位置获取失败，使用杭州默认中心', icon: 'none', duration: 2500 })
      loadPlaces()
    } else if (locationStatus === 'ok') {
      // 拿到真实坐标 → 重新加载周边点位（地图 setCenter/setZoom 由 MapCanvas 内部处理）
      loadPlaces()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationStatus])

  const filteredBasePlaces = useMemo(() => {
    return sortPlaces(
      places
        .filter((place) => displaySourceCount(place) > 0)
        .filter((place) => matchesCategory(place, category))
        .filter((place) => matchesFacility(place, facilityFilter))
        .filter((place) => inTimeRange(place, timeRange))
    )
  }, [places, category, facilityFilter, timeRange])

  const filteredAiCandidates = useMemo(() => {
    return sortPlaces(
      aiCandidates
        .map(normalizeAiSpot)
        .filter((place) => displaySourceCount(place) > 0)
        .filter((place) => matchesCategory(place, category))
        .filter((place) => matchesFacility(place, facilityFilter))
        .filter((place) => inTimeRange(place, timeRange))
    )
  }, [aiCandidates, category, facilityFilter, timeRange])

  const visiblePlaces = useMemo(() => {
    const merged = new Map<string, Place>()
    for (const place of filteredBasePlaces) merged.set(`${place.name}-${place.latitude}-${place.longitude}`, place)
    for (const place of filteredAiCandidates) merged.set(`${place.name}-${place.latitude}-${place.longitude}`, place)
    return sortPlaces(Array.from(merged.values()).filter((place) => displaySourceCount(place) > 0))
  }, [filteredBasePlaces, filteredAiCandidates])

  // spec 001-fix-source-geo-filter / FR-010：空状态文案区分两种场景
  // - 有地理意图（geocoder != null）但 DB 没数据 → "该地区暂无点位，AI 仍在为你联网搜索"
  // - 无地理意图 → 保持原文案
  const emptyStateText = searchMetadata?.geocoder
    ? `该地区${searchMetadata.detected_place ? `（${searchMetadata.detected_place}）` : ''}暂无点位，AI 仍在为你联网搜索`
    : '暂无满足筛选条件的点位。'

  async function runSearch(overrideQuery?: string) {
    const text = (overrideQuery ?? query).trim()
    if (!text) return
    if (overrideQuery && overrideQuery !== query) {
      setQuery(overrideQuery)
    }
    // 7.5-D：本次搜索序列号；后台 polling 完成时校验这个，过期就丢弃
    const mySeq = ++searchSeqRef.current
    setSearching(true)
    setHasSearched(true)
    setWarning('')
    setWarningCode(null)

    // spec 001-fix-source-geo-filter: 搜索时重新拉 places 用 q，让后端按地理意图过滤
    // 否则 places 仍是初始定位时拉的（杭州），与搜索词不匹配
    void loadPlaces(text)

    // 7.5-B：用 SSE 流式接口替代阻塞调用
    // 阶段进度由后端事件驱动（search_start / web_search_* / extract_*），不再用定时器猜阶段
    // 起秒数计时显示在阶段文案后面，让用户看到"时间还在走"
    const startMs = Date.now()
    const fmtElapsed = () => `（${Math.floor((Date.now() - startMs) / 1000)}s）`
    const STAGE_TEXT: Record<string, string> = {
      search_start: '正在联网检索…',
      web_search_in_progress: '正在准备联网工具…',
      web_search_searching: '正在搜索网页…',
      web_search_completed: '正在整理 AI 回答…',
      extract_start: '正在抽取候选点位…',
      extract_done: '即将完成…',
    }
    // 后端事件可能稀疏，用秒数计时兜底防止用户以为卡死
    const elapsedTimer = setInterval(() => {
      setProgress((prev) => {
        // 仅在仍有阶段文案时刷新秒数（complete 后 setProgress('') 会被打断）
        if (!prev) return prev
        const stageBase = prev.replace(/（\d+s）$/, '')
        return `${stageBase}${fmtElapsed()}`
      })
    }, 1000)
    setProgress(`${STAGE_TEXT.search_start}${fmtElapsed()}`)

    let typedSoFar = ''
    const incomingSources: SourceItem[] = []
    const seenCitationUrls = new Set<string>()

    try {
      await aiSearchStream(
        { q: text, limit: 12, radius_km: radiusKm },
        (evt) => {
          // 1) 阶段事件 → 进度文案
          const stageText = STAGE_TEXT[evt.type]
          if (stageText) {
            setProgress(`${stageText}${fmtElapsed()}`)
          }

          // 1.5) search_start → 同步搜索中心，让地图视野立即跳到目标地名
          if (evt.type === 'search_start' && evt.data?.search_center) {
            setSearchCenter({
              lat: evt.data.search_center.lat,
              lon: evt.data.search_center.lon,
              name: evt.data.detected_place,
            })
          }

          // 2) text_delta → 打字机增量
          if (evt.type === 'text_delta') {
            typedSoFar += evt.data.delta
            setAnswer({ text: typedSoFar, sources: incomingSources.slice() })
          }

          // 3) citation → 信源 chip 立刻可点
          if (evt.type === 'citation') {
            const url = evt.data.url
            if (url && !seenCitationUrls.has(url)) {
              seenCitationUrls.add(url)
              incomingSources.push({
                url,
                title: (evt.data.title as string) || url,
                domain: (() => {
                  try { return new URL(url).hostname } catch { return undefined }
                })(),
              })
              setAnswer({ text: typedSoFar, sources: incomingSources.slice() })
            }
          }

          // 4) complete → 用后端聚合后的权威数据覆盖（spots / unmapped / warning_code）
          if (evt.type === 'complete') {
            const data = evt.data
            setAnswer(data.answer || { text: typedSoFar, sources: incomingSources })
            setAiCandidates((data.spots || []).map(normalizeAiSpot).filter((place) => displaySourceCount(place) > 0))
            setUnmapped(data.unmapped_candidates || [])
            setCategory('全部') // T7：搜索后切回"全部"
            setTimeRange('all') // 搜索后自动放宽时间——AI 信源时间可能临界过期（如大庆日报 2025-05-04 距今 384d 超「近一年」1 天就被全剔），用户搜出来看不到 marker 体验差。默认放宽，用户想收窄手动调。
            if (data.warning) setWarning(data.warning)
            setWarningCode((data.warning_code as any) || null)
            // 小程序场景下 aiSearchStream 走非流式降级（client.ts:109）只发 complete、不发 search_start，
            // 导致 setSearchCenter 漏调 → 地图视野不跳到 detected_place。这里补一份读取，
            // 让小程序也能跳过去（stream 模式下 search_start 已先处理过、这里重复设也无害）。
            //
            // spec-017: unrecognized_location 时后端返回 search_center=null，下面 truthy 检查
            // 自然跳过 setSearchCenter → 地图视野保持不变（spec FR-009）。无需额外分支。
            const sb = (data as any).source_breakdown
            if (sb?.search_center) {
              setSearchCenter({
                lat: sb.search_center.lat,
                lon: sb.search_center.lon,
                name: sb.detected_place,
              })
            }

            // 7.5-D：extract 已改后台跑，complete 时 spots 通常为空+extract_pending=True
            // → 启动 polling，后台 extract 完成后补齐 marker
            // eslint-disable-next-line no-console
            console.log('[7.5-D] complete event:', { extract_pending: data.extract_pending, extract_cache_key: data.extract_cache_key })
            if (data.extract_pending && data.extract_cache_key) {
              void pollExtractAndMerge(data.extract_cache_key, mySeq)
            } else if (data.warning_code !== 'unrecognized_location') {
              // spec-017: unrecognized_location 是合法的"无 polling"场景（后端直接短路返回），不该报警
              // eslint-disable-next-line no-console
              console.warn('[7.5-D] complete 没含 extract_pending/cache_key，polling 不会启动！')
            }
          }

          // 5) error → 错误文案
          if (evt.type === 'error') {
            setWarning(evt.data.warning)
            setWarningCode(evt.data.warning_code as any)
          }
        },
      )
    } catch (error) {
      // 7.5-B fallback：stream 整体失败回到老阻塞接口（保留 V2 DB-first 兜底）
      try {
        const result = await unifiedSearch(text, 12, radiusKm, userCoord.lat, userCoord.lon)
        setAnswer(result.answer || null)
        setAiCandidates((result.spots || []).map(normalizeAiSpot).filter((p) => displaySourceCount(p) > 0))
        setUnmapped(result.unmapped_candidates || [])
        setCategory('全部')
        const sb = (result as any).source_breakdown
        if (sb?.search_center) {
          setSearchCenter({ lat: sb.search_center.lat, lon: sb.search_center.lon, name: sb.detected_place })
        }
        if (result.warning) setWarning(result.warning)
        setWarningCode((result as any).warning_code || null)
      } catch (fallbackError) {
        setWarning(fallbackError instanceof Error ? fallbackError.message : 'AI 搜索失败')
        setWarningCode('network_error')
        setAnswer(null)
        setAiCandidates([])
        setUnmapped([])
      }
    } finally {
      clearInterval(elapsedTimer)
      setProgress('')
      setSearching(false)
    }
  }

  /**
   * 7.5-D: 后台 extract 任务的轮询补齐。
   *
   * SSE 主流在 search_done 后立即结束（complete 含 extract_pending=True），用户已经看到
   * answer + 信源，setSearching(false) 后地图允许操作。这个函数 fire-and-forget 跑在后台，
   * 每 2 秒 poll 一次 extract-result，直到 ready=True 或超过 120s。拿到后用 spots / unmapped
   * 补齐 aiCandidates，地图上 marker 才入图。
   *
   * 用 mySeq 防"过期 polling 覆盖新搜索"：用户在 polling 期间发新搜索时 searchSeqRef 递增，
   * 旧 polling 检测到 mySeq !== searchSeqRef.current 就静默退出。
   */
  async function pollExtractAndMerge(cacheKey: string, mySeq: number) {
    const POLL_INTERVAL_MS = 2000
    const MAX_TRIES = 90 // 上限 180s（覆盖 extract 120s timeout + 一些缓冲）
    // eslint-disable-next-line no-console
    console.log(`[7.5-D poll] start mySeq=${mySeq} key=${cacheKey.slice(0, 12)}...`)
    const startedAt = Date.now()
    // UX：polling 期间显示轻量"AI 正在精确定位..."进度，避免用户以为卡死
    setProgress('AI 正在精确定位点位坐标…（地图 marker 稍后入图）')
    try {
      for (let i = 0; i < MAX_TRIES; i++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
        if (mySeq !== searchSeqRef.current) {
          // eslint-disable-next-line no-console
          console.log(`[7.5-D poll] stale (mySeq=${mySeq}, current=${searchSeqRef.current}), abort`)
          return
        }
        const elapsedS = Math.floor((Date.now() - startedAt) / 1000)
        setProgress(`AI 正在精确定位点位坐标…（${elapsedS}s）`)
        try {
          const r = await getExtractResult(cacheKey)
          // eslint-disable-next-line no-console
          console.log(`[7.5-D poll] try ${i + 1}/${MAX_TRIES} ready=${r.ready} spots=${(r.spots || []).length} timeout=${r.extract_timeout}`)
          if (!r.ready) continue
          if (mySeq !== searchSeqRef.current) return // 拿到结果时也再校验一次
          if (r.spots && r.spots.length > 0) {
            const transformed = r.spots.map(normalizeAiSpot).filter((p) => displaySourceCount(p) > 0)
            // eslint-disable-next-line no-console
            console.log(`[7.5-D poll] setAiCandidates with ${transformed.length} spots (filtered from ${r.spots.length})`)
            setAiCandidates(transformed)
          }
          if (r.unmapped_candidates && r.unmapped_candidates.length > 0) {
            setUnmapped(r.unmapped_candidates)
          }
          if (r.extract_timeout) {
            setWarning('AI 已找到网页信源，但点位结构化超时了；可以先点开下方信源链接自己查看，或稍后重试同一搜索。')
            setWarningCode('extract_timeout')
          }
          return
        } catch {
          // 单次 poll 失败就继续，不放弃整体（网络抖动很常见）
        }
      }
    } finally {
      // polling 结束（成功/超时/被新搜索打断），都清进度文案
      if (mySeq === searchSeqRef.current) setProgress('')
    }
  }

  async function openDetail(place: Place) {
    if (displaySourceCount(place) <= 0) {
      setSelectedPlace(null)
      setWarning('该点位没有公开网页来源，已隐藏。')
      return
    }
    setSelectedPlace(place)
    if (!isPersistedPlace(place)) return
    const placeId = place.id as string
    try {
      setSelectedPlace(await getPlaceDetail(placeId))
    } catch {
      setSelectedPlace(null)
      setWarning('该点位没有公开网页来源，已隐藏。')
    }
  }

  async function quickFeedback(payload: Parameters<typeof submitFeedback>[1]) {
    if (!selectedPlace || !isPersistedPlace(selectedPlace)) {
      Taro.showToast({ title: '该来源结果尚未保存，暂不能反馈', icon: 'none' })
      return
    }
    const placeId = selectedPlace.id as string
    try {
      const result = await submitFeedback(placeId, payload)
      setSelectedPlace({ ...selectedPlace, ...result.place })
      Taro.showToast({ title: '已记录', icon: 'success' })
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '提交失败', icon: 'none' })
    }
  }

  function showFeatureHint(title: string) {
    Taro.showToast({ title, icon: 'none' })
  }

  // T7 D7-1 A：初始不再 loadPlaces；用户搜索后才有点位
  // （旧代码自动加载 61 个底库点，导致空白搜索框却满图 marker，违背"搜索驱动"原则）

  // P2-4-F: amap init / setCenter / markers 渲染全部搬到 MapCanvas 组件
  // mapRef / markersRef / clusterRef / 两个 useEffect 已在 MapCanvas 内部

  const statusMessage = warning || progress

  return (
    <View className='page'>
      <View className='map-wrap'>
        <MapCanvas
          places={visiblePlaces}
          searchCenter={searchCenter}
          userCoord={userCoord}
          locationStatus={locationStatus}
          onMarkerClick={openDetail}
          onMapError={setMapError}
        />
        {(mapError || loading) && (
          <View className='map-status'>
            <Text>{loading ? '正在加载候选点位' : mapError}</Text>
          </View>
        )}
        {/* T7 D7-1 A：用户还没搜索时，在地图中央显示引导卡片（P2-4-C 抽到 EmptyHero）*/}
        {!hasSearched && !searching && !mapError && !heroDismissed && (
          <EmptyHero onQueryPick={(q) => runSearch(q)} onDismiss={() => setHeroDismissed(true)} />
        )}
      </View>

      {/* T7 D7-2 B：搜过后顶部面板折叠为窄条，给地图让位 */}
      <View className={`top-panel ${hasSearched ? 'collapsed' : ''}`}>
        <View className='nav-row'>
          <View className='mode-tabs'>
            <Button className={`mode-tab ${viewMode === 'map' ? 'active' : ''}`} onClick={() => setViewMode('map')}>地图</Button>
            <Button className={`mode-tab ${viewMode === 'list' ? 'active' : ''}`} onClick={() => setViewMode('list')}>列表</Button>
          </View>
          {/* 发布/筛选按钮仅在搜索后显示，避免空状态下视觉干扰 */}
          {hasSearched && (
            <View className='top-actions'>
              <Button className='text-link' onClick={() => showFeatureHint('发布入口后续接入')}>发布</Button>
              <Button className='icon-entry' onClick={() => showFeatureHint('可用右侧设施按钮快速筛选')}>筛选</Button>
            </View>
          )}
        </View>
        <SearchBar
          query={query}
          searching={searching}
          progress={progress}
          onQueryChange={setQuery}
          onSearch={() => runSearch()}
        />
        {/* T7 D7-4 B：搜索完成后展示结果分类 Tab，按 AI 返回的 type 二次筛选 */}
        {hasSearched && !searching && visiblePlaces.length > 0 && (
          <View className='result-tabs'>
            {RESULT_TABS.map((tab) => (
              <Button
                key={tab.key}
                className={`result-tab ${category === tab.key ? 'active' : ''}`}
                onClick={() => setCategory(tab.key)}
              >
                {tab.label}
              </Button>
            ))}
          </View>
        )}
      </View>

      {/* T7 收尾：左侧悬浮工具仅在搜索后显示，空状态时把地图让出来 */}
      {hasSearched && (
        <View className='map-left-tools'>
          <Button className='floating-list-btn' onClick={() => setViewMode('list')}>打开列表</Button>
          <View className='range-bubble'>
            <Text className='range-icon'>⌕</Text>
            <Text>{radiusKm}KM</Text>
          </View>
        </View>
      )}

      {/* 右侧设施筛选条同理，仅在搜索后显示 */}
      {hasSearched && (
        <View className='facility-rail'>
          {FACILITY_FILTERS.map((item) => (
            <Button
              key={item.key}
              className={`rail-btn ${facilityFilter === item.key ? 'active' : ''}`}
              onClick={() => setFacilityFilter(item.key)}
            >
              <Text className='rail-main'>{item.label}</Text>
              <Text className='rail-hint'>{item.hint}</Text>
            </Button>
          ))}
        </View>
      )}

      <AnswerPanel
        answer={answer}
        warningCode={warningCode}
        filteredAiCandidatesCount={filteredAiCandidates.length}
        unmappedCount={unmapped?.length || 0}
      />

      {viewMode === 'list' && (
        <ScrollView className='list-panel' scrollY>
          {/* spec-010 R1：内边距挪到 .list-panel-inner，小程序 <scroll-view> 自身不支持 padding */}
          <View className='list-panel-inner'>
            {(visiblePlaces.length > 0 || !!unmapped?.length) && <AiRiskNotice />}
            <View className='list-header'>
              <Text className='list-section-title'>来源点位 {visiblePlaces.length}</Text>
              <Button className='switch-btn' onClick={() => setViewMode('map')}>地图</Button>
            </View>
            {!visiblePlaces.length && <View className='empty-card list-empty'>{emptyStateText}</View>}
            {visiblePlaces.map((place) => (
              <PlaceCard key={placeKey(place)} place={place} onClick={() => openDetail(place)} />
            ))}
            {!!unmapped?.length && <Text className='list-section-title'>来源线索 {unmapped.length}</Text>}
            {!!unmapped?.length && (
              <View className='list-unmapped-grid'>
                {unmapped.map((item) => (
                  <SourceLeadCard key={item.name} item={item} />
                ))}
              </View>
            )}
            {!!statusMessage && (
              <View className={`inline-status ${warning ? 'warning' : ''} ${warningCode === 'extract_timeout' ? 'extract-timeout' : ''}`}>
                {warningCode === 'extract_timeout' && <Text className='inline-status-icon'>⏱️</Text>}
                <Text>{statusMessage}</Text>
              </View>
            )}
          </View>
        </ScrollView>
      )}

      {viewMode === 'map' && hasSearched && (
        <View className='bottom-sheet'>
          <View className='sheet-header'>
            <View>
              <Text className='sheet-title'>来源点位 {visiblePlaces.length}</Text>
              <Text className='subtle'>网页来源 {factSources(answer?.sources).length || visiblePlaces.reduce((sum, place) => sum + displaySourceCount(place), 0)} · {radiusKm}km</Text>
            </View>
            <Button className='switch-btn' onClick={() => setViewMode('list')}>列表</Button>
          </View>
          <View className='dock-filter-row'>
            <View className='time-filter'>
              {TIME_RANGES.map((item) => (
                <Button key={item.key} className={`pill ${timeRange === item.key ? 'selected' : ''}`} onClick={() => setTimeRange(item.key)}>
                  {item.label}
                </Button>
              ))}
            </View>
          </View>
          {!!statusMessage && (
            <View className={`sheet-status ${warning ? 'warning' : ''} ${warningCode === 'extract_timeout' ? 'extract-timeout' : ''}`}>
              {warningCode === 'extract_timeout' && <Text className='sheet-status-icon'>⏱️</Text>}
              <Text>{statusMessage}</Text>
            </View>
          )}
          {(visiblePlaces.length > 0 || !!unmapped?.length) && <AiRiskNotice />}
          <ScrollView className='card-row' scrollX>
            {visiblePlaces.map((place) => (
              <PlaceCard key={placeKey(place)} place={place} onClick={() => openDetail(place)} compact />
            ))}
            {!visiblePlaces.length && <View className='empty-card'>{emptyStateText}</View>}
          </ScrollView>
          {!!unmapped?.length && (
            <View className='unmapped'>
              <Text className='unmapped-title'>来源线索 {unmapped.length}</Text>
              <ScrollView className='unmapped-list' scrollX>
                {unmapped.map((item) => (
                  <SourceLeadCard key={item.name} item={item} />
                ))}
              </ScrollView>
            </View>
          )}
        </View>
      )}

      {selectedPlace && (
        <PlaceDetailDrawer
          place={selectedPlace}
          viewedSources={viewedSources}
          onClose={() => setSelectedPlace(null)}
          onSourceViewed={markSourceViewed}
          onQuickFeedback={quickFeedback}
        />
      )}

      {/* spec-017 B 方案：链接二维码 modal（仅小程序端弹出；H5 端 window.open 不会触发） */}
      <QRCodeModal url={qrModalUrl} onClose={() => setQrModalUrl(null)} />
    </View>
  )
}
