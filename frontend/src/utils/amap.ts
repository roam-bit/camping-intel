import Taro from '@tarojs/taro'
import type { Place } from '../types'
import { wgs84ToGcj02 } from './coords'

declare global {
  interface Window {
    AMap?: any
    _AMapSecurityConfig?: { securityJsCode?: string }
  }
}

const AMAP_KEY = process.env.TARO_APP_AMAP_WEB_KEY || ''
const AMAP_SECURITY_CODE = process.env.TARO_APP_AMAP_SECURITY_CODE || ''

let loadingPromise: Promise<any> | null = null

/** `.env.example` 里的占位符原样留着时，等同于「没配 key」。
 *  不这样判的话：占位符是非空字符串 → 当成有 key → 去请求高德 → 高德拒绝但脚本仍 200
 *  → window.AMap 为 undefined → 页面抛 `Cannot read properties of undefined (reading 'Map')`。
 *  新人第一次跑必踩，且报错完全看不出是 key 的问题。 */
function isPlaceholder(v: string) {
  return /^your[-_]/i.test(v.trim())
}

export function hasAmapKey() {
  return Boolean(AMAP_KEY) && !isPlaceholder(AMAP_KEY)
}

export function loadAmap() {
  if (typeof window === 'undefined') return Promise.reject(new Error('高德地图只在 H5 浏览器环境初始化'))
  if (window.AMap) return Promise.resolve(window.AMap)
  if (!hasAmapKey()) return Promise.reject(new Error('缺少 TARO_APP_AMAP_WEB_KEY，无法加载高德地图'))
  if (AMAP_SECURITY_CODE) {
    window._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_CODE }
  }
  if (!loadingPromise) {
    loadingPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_KEY}&plugin=AMap.Scale,AMap.ToolBar,AMap.MarkerCluster`
      script.async = true
      // 注意：key 无效时高德仍会返回 200 + 一段什么都不挂载的脚本，onload 照样触发。
      // 不校验 window.AMap 就 resolve(undefined)，调用方 `new AMap.Map()` 直接抛
      // `Cannot read properties of undefined (reading 'Map')` —— 报错和真实原因毫无关系。
      script.onload = () =>
        window.AMap
          ? resolve(window.AMap)
          : reject(new Error('高德 Key 无效或已过期（服务端拒绝了这个 Key）'))
      script.onerror = () => reject(new Error('高德地图 JS API 加载失败，检查网络'))
      document.head.appendChild(script)
    })
  }
  return loadingPromise
}

export function toAmapPosition(place: Pick<Place, 'longitude' | 'latitude'>): [number, number] {
  return wgs84ToGcj02(place.longitude, place.latitude)
}

export function openAmapNavigation(place: Place) {
  const [lon, lat] = toAmapPosition(place)
  // 小程序端无 window，window.open 打不开高德网页导航 —— 改用 Taro.openLocation
  // 打开微信内置位置查看页，用户可在那里「到这里去」唤起系统地图导航（spec-012 US5）。
  if (process.env.TARO_ENV !== 'h5') {
    Taro.openLocation({ longitude: lon, latitude: lat, name: place.name, scale: 14 })
    return
  }
  const name = encodeURIComponent(place.name)
  const url = `https://uri.amap.com/navigation?to=${lon},${lat},${name}&mode=car&policy=1&src=camping-ai&coordinate=gaode`
  if (typeof window !== 'undefined') window.open(url, '_blank')
}
