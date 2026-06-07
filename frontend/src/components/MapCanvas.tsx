/**
 * P2-4-F: 高德地图容器 + marker 渲染。
 *
 * 把地图的 3 个 ref（map/markers/cluster）+ 3 个 useEffect（init / setCenter / markers）
 * 一起搬进来。父组件只通过 props 传 places / searchCenter / userCoord / locationStatus
 * 和回调（点 marker / 报错），不再持有 amap 句柄。
 */
import { useEffect, useRef } from 'react'
import { View } from '@tarojs/components'
import { hasAmapKey, loadAmap, toAmapPosition } from '../utils/amap'
import { displaySourceCount } from '../utils/place-helpers'
import type { MapCanvasProps } from './MapCanvas.types'

export function MapCanvas({
  places,
  searchCenter,
  userCoord,
  locationStatus,
  onMarkerClick,
  onMapError,
}: MapCanvasProps) {
  const mapRef = useRef<any>(null)
  const markersRef = useRef<any[]>([])
  const clusterRef = useRef<any>(null)

  // 1) 初始化高德 SDK + Map 实例（只跑一次）
  useEffect(() => {
    if (process.env.TARO_ENV !== 'h5') return
    if (!hasAmapKey()) {
      onMapError('缺少 TARO_APP_AMAP_WEB_KEY，H5 暂无法显示高德地图')
      return
    }
    loadAmap()
      .then((AMap) => {
        if (mapRef.current) return
        mapRef.current = new AMap.Map('amap-container', {
          center: toAmapPosition({ longitude: userCoord.lon, latitude: userCoord.lat }),
          zoom: 9,
          resizeEnable: true,
          viewMode: '2D',
        })
        mapRef.current.addControl(new AMap.Scale())
        mapRef.current.addControl(new AMap.ToolBar({ position: 'RT' }))
      })
      .catch((error: unknown) => onMapError(error instanceof Error ? error.message : '高德地图加载失败'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 2) P2-5: 用户定位 ok 时把地图 center 跳到真实位置 + zoom 拉近
  useEffect(() => {
    if (locationStatus !== 'ok') return
    if (mapRef.current && typeof mapRef.current.setCenter === 'function') {
      try {
        mapRef.current.setCenter([userCoord.lon, userCoord.lat])
        mapRef.current.setZoom?.(12)
      } catch {
        /* SDK 没就绪就忽略 */
      }
    }
  }, [locationStatus, userCoord.lat, userCoord.lon])

  // 3) places / searchCenter 变化 → 重新渲染 marker + fitView
  useEffect(() => {
    if (!mapRef.current || process.env.TARO_ENV !== 'h5') return
    const AMap = (window as any).AMap
    if (!AMap) return
    if (clusterRef.current?.setMap) clusterRef.current.setMap(null)
    if (markersRef.current.length) mapRef.current.remove(markersRef.current)
    const markers = places.map((place) => {
      const [lon, lat] = toAmapPosition(place)
      const marker = new AMap.Marker({
        position: [lon, lat],
        offset: new AMap.Pixel(-18, -42),
        content: `<div class="map-poi-marker source"><span class="map-poi-icon"></span><span class="map-poi-score">${displaySourceCount(place)}</span></div>`,
      })
      marker.on('click', () => onMarkerClick(place))
      return marker
    })
    markersRef.current = markers
    mapRef.current.add(markers)
    // 优先级调换（修 bug: 搜「塔克拉玛干」marker 落新疆，但地图卡在之前搜的南京）：
    // - 有 marker 时优先 fitView，让地图自动飞到真实点位范围（最准）
    // - 0 marker 才用 searchCenter 兜底（让用户知道"区域识别到了，只是无结构化结果"）
    // 原逻辑反过来：searchCenter 优先 → 后端 detect_place_center 未覆盖的地名（如塔克拉玛干、
    // 漠河、雅鲁藏布江）会让 searchCenter 沿用前端默认（杭州 / 用户定位）→ 地图飞错地方。
    if (markers.length > 0) {
      mapRef.current.setFitView(markers, false, [120, 120, 300, 120])
    } else if (searchCenter) {
      mapRef.current.setZoomAndCenter(10, [searchCenter.lon, searchCenter.lat])
    }
  }, [places, searchCenter, onMarkerClick])

  return <View id='amap-container' className='map-canvas' />
}
