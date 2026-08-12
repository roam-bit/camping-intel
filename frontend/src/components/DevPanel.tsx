/**
 * 开发者抽屉（仅 H5；入口是顶栏小齿轮）。2026-06-12 用户需求：
 * "显示/搜索数量不够，我知道是系统提示词导致的，需要个开发者界面"。
 *
 * 三块能力（按「做轻」纪律，全部只读后端、参数只进请求不改服务端状态）：
 *  1. 参数旋钮：搜索数量 limit（写进 AI prompt 的"最多列出 N 个候选"）+ 搜索半径，
 *     localStorage 持久化，下次会话仍生效
 *  2. 召回诊断：最近一次搜索的分层数据（DB 命中/AI 抽取/策略/耗时）——
 *     回答"为什么只有这么几个点位：瓶颈在哪一层"
 *  3. Prompt 预览：当前参数下系统提示词的真实样子（后端只读接口）
 */
import { useEffect, useState } from 'react'
import { Button, ScrollView, Text, View } from '@tarojs/components'
import { getDevPromptPreview } from '../api/client'

export const LIMIT_OPTIONS = [6, 12, 24, 36, 50]
export const RADIUS_OPTIONS = [40, 80, 120, 200]

/** 最近一次搜索的调试快照（index.tsx 在 complete/fallback/extract 各阶段填充） */
export interface SearchDebugInfo {
  query?: string
  strategy?: string
  detectedPlace?: string | null
  centerSource?: string
  dbHits?: number
  aiSpots?: number
  threshold?: number
  spotsShown?: number
  warningCode?: string | null
  elapsedSeconds?: number | null
  extractPending?: boolean
  finishedAt?: string
}

export interface DevPanelProps {
  open: boolean
  onClose: () => void
  limit: number
  radiusKm: number
  onLimitChange: (v: number) => void
  onRadiusChange: (v: number) => void
  debug: SearchDebugInfo | null
  /** 当前搜索框 query（prompt 预览用；空则用默认示例） */
  query: string
}

export function DevPanel({ open, onClose, limit, radiusKm, onLimitChange, onRadiusChange, debug, query }: DevPanelProps) {
  const [prompt, setPrompt] = useState('')
  const [promptError, setPromptError] = useState('')

  // 打开抽屉或 limit/query 变化时刷新 prompt 预览
  useEffect(() => {
    if (!open) return
    let stale = false
    getDevPromptPreview(query.trim() || '杭州周边免费露营地', limit)
      .then((r) => { if (!stale) { setPrompt(r.prompt); setPromptError('') } })
      .catch((e) => { if (!stale) setPromptError(e instanceof Error ? e.message : '预览接口不可用') })
    return () => { stale = true }
  }, [open, limit, query])

  if (!open) return null

  return (
    <View className='dev-mask' onClick={onClose}>
      <View className='dev-drawer' onClick={(e) => e.stopPropagation()}>
        <View className='dev-header'>
          <Text className='dev-title'>⚙️ 开发者面板</Text>
          <Button className='dev-close' onClick={onClose}>×</Button>
        </View>
        <ScrollView className='dev-body' scrollY>
          <View className='dev-body-inner'>

          <Text className='dev-section-title'>召回参数</Text>
          <Text className='dev-field-label'>搜索数量上限（写进 AI 提示词的"最多列出 N 个候选"）</Text>
          <View className='dev-chip-row'>
            {LIMIT_OPTIONS.map((v) => (
              <Button key={v} className={`dev-chip ${limit === v ? 'on' : ''}`} onClick={() => onLimitChange(v)}>{v}</Button>
            ))}
          </View>
          <Text className='dev-field-label'>搜索半径（km）</Text>
          <View className='dev-chip-row'>
            {RADIUS_OPTIONS.map((v) => (
              <Button key={v} className={`dev-chip ${radiusKm === v ? 'on' : ''}`} onClick={() => onRadiusChange(v)}>{v}</Button>
            ))}
          </View>
          <Text className='dev-hint'>
            ⓘ limit 是召回上限不是保底——实际数量还取决于 DB 存量与 AI 抽取结果，瓶颈看下方诊断。改完重新搜索生效，配置已本地持久化。
          </Text>

          <Text className='dev-section-title'>召回诊断（最近一次搜索）</Text>
          {debug ? (
            <View className='dev-kv-list'>
              <View className='dev-kv'><Text className='k'>query</Text><Text className='v'>{debug.query || '—'}</Text></View>
              <View className='dev-kv'><Text className='k'>策略</Text><Text className='v'>{debug.strategy || '—'}{debug.extractPending ? '（AI 后台抽取中）' : ''}</Text></View>
              <View className='dev-kv'><Text className='k'>识别地名</Text><Text className='v'>{debug.detectedPlace || '—'}（{debug.centerSource || '?'}）</Text></View>
              <View className='dev-kv'><Text className='k'>DB 命中</Text><Text className='v'>{debug.dbHits ?? '—'}（秒回阈值 {debug.threshold ?? '?'}）</Text></View>
              <View className='dev-kv'><Text className='k'>AI 抽取</Text><Text className='v'>{debug.aiSpots ?? '—'}</Text></View>
              <View className='dev-kv'><Text className='k'>当前展示</Text><Text className='v'>{debug.spotsShown ?? '—'}（再经时间/设施筛选）</Text></View>
              <View className='dev-kv'><Text className='k'>耗时</Text><Text className='v'>{debug.elapsedSeconds != null ? `${debug.elapsedSeconds}s` : '—'}</Text></View>
              {!!debug.warningCode && <View className='dev-kv'><Text className='k'>warning</Text><Text className='v'>{debug.warningCode}</Text></View>}
            </View>
          ) : (
            <Text className='dev-hint'>还没搜索过——点首页示例按钮跑一次，这里会显示每一层的召回数据。</Text>
          )}

          <Text className='dev-section-title'>系统提示词预览（只读）</Text>
          {promptError ? (
            <Text className='dev-hint'>⚠ {promptError}</Text>
          ) : (
            <Text className='dev-prompt'>{prompt || '加载中…'}</Text>
          )}
          </View>
        </ScrollView>
      </View>
    </View>
  )
}
