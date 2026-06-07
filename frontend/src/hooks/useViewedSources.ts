/**
 * P2-4-G: 用户"求证"进度（已点过的信源 url 集合）。
 *
 * - mount 时从 localStorage 读初值
 * - markSourceViewed 增量打点 + 持久化
 * - 用于详情抽屉「已查看 N/M」+ 导航按钮"已求证"高亮
 */
import { useCallback, useState } from 'react'
import { loadViewedSources, persistViewedSources } from '../utils/place-helpers'

export function useViewedSources() {
  const [viewedSources, setViewedSources] = useState<Set<string>>(() => loadViewedSources())

  const markSourceViewed = useCallback((url: string) => {
    if (!url) return
    setViewedSources((prev) => {
      if (prev.has(url)) return prev
      const next = new Set(prev)
      next.add(url)
      persistViewedSources(next)
      return next
    })
  }, [])

  return { viewedSources, markSourceViewed }
}
