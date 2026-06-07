/**
 * P2-5: 拿用户真实地理位置（H5 端调浏览器 geolocation，小程序端调 Taro.getLocation）。
 *
 * 失败 / 未授权时回落到杭州默认中心，并暴露 status 给 UI 显示提示。
 *
 * 用法:
 *   const { coord, status } = useUserLocation()
 *   // coord 一定有值（默认杭州），status 告诉你是真实定位还是回落
 *
 * status 取值:
 *   'idle'    - 还没尝试
 *   'pending' - 正在请求权限 / 等定位
 *   'ok'      - 拿到真实坐标
 *   'denied'  - 用户拒绝
 *   'error'   - 其他错误（设备不支持 / 超时）
 *   'fallback' - 综合状态：UI 可统一用这个判断"是不是默认值"
 */
import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'

export const HANGZHOU_FALLBACK = { lat: 30.2741, lon: 120.1551 }

export type LocationStatus = 'idle' | 'pending' | 'ok' | 'denied' | 'error'

export interface UseUserLocationResult {
  coord: { lat: number; lon: number }
  status: LocationStatus
  isFallback: boolean
}

export function useUserLocation(): UseUserLocationResult {
  const [coord, setCoord] = useState(HANGZHOU_FALLBACK)
  const [status, setStatus] = useState<LocationStatus>('idle')

  useEffect(() => {
    let cancelled = false
    setStatus('pending')

    // 定位超时保护（spec-013 D3）：防 Taro.getLocation 挂起（既不 resolve 也不
    // reject）导致 status 永远卡 'pending'。8 秒拿不到就按失败处理、coord 保持杭州默认。
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    const timeoutPromise = new Promise<never>((_, reject) => {
      timeoutId = setTimeout(() => reject(new Error('定位超时')), 8000)
    })

    // Taro.getLocation 在 H5 端会调 navigator.geolocation；weapp 端调微信 API
    // type='wgs84' 让坐标系与后端 places.latitude/longitude（WGS84）一致
    Promise.race([Taro.getLocation({ type: 'wgs84' }), timeoutPromise])
      .then((res: { latitude: number; longitude: number }) => {
        if (cancelled) return
        // 简单合理性检查：忽略明显异常坐标（地球外 / 0,0 之类）
        if (
          typeof res.latitude !== 'number' ||
          typeof res.longitude !== 'number' ||
          Math.abs(res.latitude) > 90 ||
          Math.abs(res.longitude) > 180 ||
          (res.latitude === 0 && res.longitude === 0)
        ) {
          setStatus('error')
          return
        }
        setCoord({ lat: res.latitude, lon: res.longitude })
        setStatus('ok')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        // navigator.geolocation 拒绝码 1=PERMISSION_DENIED, 2=POSITION_UNAVAILABLE, 3=TIMEOUT
        const code = (err as { errMsg?: string; code?: number })?.code
        const msg = (err as { errMsg?: string })?.errMsg || String(err)
        if (code === 1 || /denied|permission/i.test(msg)) {
          setStatus('denied')
        } else {
          setStatus('error')
        }
      })
      .finally(() => {
        if (timeoutId) clearTimeout(timeoutId)
      })

    return () => {
      cancelled = true
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [])

  return {
    coord,
    status,
    isFallback: status === 'denied' || status === 'error' || status === 'idle',
  }
}
