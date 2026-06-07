/**
 * 微信小程序端地图（spec-012 R2；spec-014 修渲染崩溃 + 视野跟随）。
 *
 * 与 H5 的 MapCanvas.tsx 同名、同 props（MapCanvasProps），Taro 编译时按平台二选一。
 * H5 端用高德 JS API（命令式）；这里用微信原生 <Map> 组件（声明式，腾讯底图）。
 *
 * 视野控制（spec-016 修真机视野不居中；上承 spec-012/014）：
 * - 原生 <map> 声明式 longitude/latitude「挂载后改值不可靠」（社区共识「地图只渲染一次」
 *   + spec-014 实测）——故视野目标变化时换 React key 强制 <Map> 卸载重挂、带新坐标重渲。
 * - include-points 设为「视野目标的包围盒」（viewIncludeBox）：原生 <map> 挂载时 fitBounds
 *   到它 → 居中到目标；且它始终非空，保留 spec-014 崩溃护栏（空数组致 fitBounds 崩）。
 * - marker 不能放任意 HTML——用 iconPath + label；带数字 id（= places 索引）。
 * - 坐标统一走 wgs84ToGcj02：高德/腾讯/小程序都用 GCJ-02 火星坐标。
 */
import { useMemo } from 'react'
import { Map } from '@tarojs/components'
import type { MapCanvasProps } from './MapCanvas.types'
import { toAmapPosition } from '../utils/amap'
import { wgs84ToGcj02 } from '../utils/coords'
import { displaySourceCount } from '../utils/place-helpers'

// marker 图标——经 config/index.js 的 copy 配置原样进包（不走 import，避免被内联成
// base64；weapp <map> 的 iconPath 不认 data URI）。路径为代码包根目录下的绝对路径。
const MARKER_ICON = '/assets/marker.png'

const DEFAULT_SCALE = 9 // 初始（未定位、未搜索）
const LOCATED_SCALE = 12 // 定位成功后
const SEARCH_SCALE = 10 // 搜索到地名但无结构化点位
const SINGLE_SCALE = 13 // 单个 marker

/**
 * 由一组 marker 点位算出地图视野（中心 + 缩放）。
 * span→scale 用经验对数映射，留 ~2x 余量；单点（span≈0）用较近的 SINGLE_SCALE。
 */
function viewForMarkers(pts: { longitude: number; latitude: number }[]) {
  const lons = pts.map((p) => p.longitude)
  const lats = pts.map((p) => p.latitude)
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const span = Math.max(maxLon - minLon, maxLat - minLat)
  return {
    longitude: (minLon + maxLon) / 2,
    latitude: (minLat + maxLat) / 2,
    scale:
      span < 0.01 ? SINGLE_SCALE : Math.min(16, Math.max(4, Math.round(Math.log2(360 / (span * 2))))),
  }
}

/**
 * spec-016：把视野目标转成 include-points 包围盒。
 * 原生 <map> 挂载时 fitBounds 到 include-points → 让它 = 视野中心附近的小框、地图即居中到目标；
 * 且 include-points 始终非空、保留 spec-014 崩溃护栏。半边长按 scale 反推（scale 越大框越小）。
 */
function viewIncludeBox(v: { longitude: number; latitude: number; scale: number }) {
  const half = 90 / Math.pow(2, v.scale)
  return [
    { latitude: v.latitude - half, longitude: v.longitude - half },
    { latitude: v.latitude + half, longitude: v.longitude + half },
  ]
}

export function MapCanvas({
  places,
  searchCenter,
  userCoord,
  locationStatus,
  onMarkerClick,
  onMapError,
}: MapCanvasProps) {
  // places → marker 数组。id = places 原始索引，onMarkerTap 据此反查。
  // 过滤坐标异常的坏点位（FR-009）—— 单个坏点不该拖垮整张地图 / fitView。
  const markers = useMemo(
    () =>
      places
        .map((place, index) => {
          if (!Number.isFinite(place.longitude) || !Number.isFinite(place.latitude)) {
            return null
          }
          const [longitude, latitude] = toAmapPosition(place)
          return {
            id: index, // 原始索引 —— onMarkerTap 用它反查 places
            longitude,
            latitude,
            iconPath: MARKER_ICON,
            width: 32,
            height: 32,
            anchor: { x: 0.5, y: 0.5 },
            // 原生 marker 不能放 HTML —— 用 label 显示信源数（H5 端是 marker 内的数字）
            label: {
              content: String(displaySourceCount(place)),
              color: '#5b66f4',
              fontSize: 11,
              bgColor: '#ffffff',
              borderRadius: 8,
              padding: 3,
              anchorX: 0,
              anchorY: -30,
            },
          }
        })
        .filter((m): m is NonNullable<typeof m> => m !== null),
    [places],
  )

  // 受控视野（中心 + 缩放，GCJ-02）。优先级：≥2 marker 包围盒 → 单 marker → 搜索中心 → 用户定位。
  const view = useMemo(() => {
    if (markers.length >= 2) {
      return viewForMarkers(markers)
    }
    if (markers.length === 1) {
      return { longitude: markers[0].longitude, latitude: markers[0].latitude, scale: SINGLE_SCALE }
    }
    if (searchCenter) {
      const [longitude, latitude] = wgs84ToGcj02(searchCenter.lon, searchCenter.lat)
      return { longitude, latitude, scale: SEARCH_SCALE }
    }
    const [longitude, latitude] = wgs84ToGcj02(userCoord.lon, userCoord.lat)
    return { longitude, latitude, scale: locationStatus === 'ok' ? LOCATED_SCALE : DEFAULT_SCALE }
  }, [markers, searchCenter, userCoord.lon, userCoord.lat, locationStatus])

  // spec-016：原生 <map> 声明式坐标「挂载后改值不生效」——视野目标变化时换 key，
  // 强制 <Map> 卸载重挂、带新坐标重新渲染一次。
  const mapKey = `map-${view.latitude.toFixed(5)}-${view.longitude.toFixed(5)}-${view.scale}`

  // 点 marker → 用 markerId（= places 索引）反查 place → 触发与 H5 一致的 onMarkerClick
  const handleMarkerTap = (e: { detail?: { markerId?: number } }) => {
    const markerId = e?.detail?.markerId
    const place = typeof markerId === 'number' ? places[markerId] : undefined
    if (place) onMarkerClick(place)
  }

  return (
    <Map
      key={mapKey}
      className='map-canvas'
      longitude={view.longitude}
      latitude={view.latitude}
      scale={view.scale}
      // Taro 的 MapProps marker/includePoints 类型较严，跨版本易漂移 —— 在组件边界做一次 any 收口
      markers={markers as any}
      includePoints={viewIncludeBox(view) as any}
      onMarkerTap={handleMarkerTap as any}
      onError={((e: any) => onMapError(e?.detail?.errMsg || '小程序地图加载失败')) as any}
      showLocation={locationStatus === 'ok'}
      enableScroll
      enableZoom
    />
  )
}
