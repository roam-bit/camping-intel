import type { Place } from '../types'
import type { LocationStatus } from '../hooks/useUserLocation'

/**
 * MapCanvas 两端共享的 props 契约（spec-012）。
 *
 * MapCanvas 有两份实现：
 * - MapCanvas.tsx        —— H5 端，高德 JS API（命令式）
 * - MapCanvas.weapp.tsx  —— 微信小程序端，原生 <Map>（声明式）
 * Taro 编译时按平台自动选文件。两份实现都用本接口，保证对 index.tsx 表现一致。
 */
export interface MapCanvasProps {
  places: Place[]
  searchCenter: { lat: number; lon: number; name?: string | null } | null
  userCoord: { lat: number; lon: number }
  /** 'ok' 时拿到真实定位 → 自动 setCenter + setZoom(12) */
  locationStatus: LocationStatus
  onMarkerClick: (place: Place) => void
  onMapError: (msg: string) => void
}
