/**
 * P2-4-D: AI 提炼结果区。
 *
 * - 显示 AI 联网搜索 + 抽取后的 answer.text 文字 + 信源 chip
 * - extract_timeout 时显示 incomplete badge + 友好降级提示
 * - 信源 chip 点击直接 openExternalUrl 外跳浏览器
 *
 * 不显示场景（由父组件控制）:
 *   warning_code in ['network_error', 'empty_answer', 'no_traceable_sources']
 *   或 answer.text 为空
 */
import { ScrollView, Text, View } from '@tarojs/components'
import type { AISearchResponse } from '../types'
import { detectPlatform, factSources, formatDate, openExternalUrl, PLATFORM_META, sourceDate, sourceUrl, stripAnswerLinkNoise } from '../utils/place-helpers'
import { AiGeneratedTag } from './AiContentLabels'

/** 平台 key → 概览 chip 的 emoji（demo2 样式） */
const PLATFORM_EMOJI: Record<string, string> = {
  xhs: '📕', douyin: '🎵', zhihu: '💬', mafengwo: '🐝',
  bilibili: '📺', weibo: '📣', gov: '🏛️', other: '🌐',
}

/** 无信息量的字段值（"来源未提到"类），条目卡里直接不显示 */
const EMPTY_VALUE_RE = /来源未提到|未提到|unknown|未知|未提供|无明确/

interface AnswerEntry {
  name: string
  /** 地址线索单独一行（往往较长，不适合做 chip） */
  addr: string | null
  /** 其余字段做成小 chip：费用 / 过夜 / 停车 / 厕所 / 水源 / 日期 */
  chips: string[]
}

/**
 * 把 AI 回答的"编号流水账"解析成结构化条目（仅 H5 展示用，解析失败回退纯文本）。
 *
 * 输入样例（已经过 stripAnswerLinkNoise，无 URL）：
 *   "1. 安顶山，地址：富阳区里山村观景台，费用：免费，可露营/过夜：允许，停车：来源未提到，
 *    厕所：公共卫生间，水源：自来水，信息日期：2026-04-07 2. 九仰坪，…"
 * 容错：键名变体（地址/地址线索、是否可露营/过夜…）、值里出现顿号、流式半截条目。
 */
function parseAnswerEntries(text: string): { preamble: string; entries: AnswerEntry[] } | null {
  // 编号分割：行首或空格后的 "N." / "N、"（条目可能挤在同一行）
  const parts = text.split(/(?:^|\n|\s)(?=\d{1,2}\s*[.、．]\s*)/)
  if (parts.length < 2) return null
  const preamble = /^\d{1,2}\s*[.、．]/.test(parts[0].trim()) ? '' : parts.shift()!.trim()
  const entries: AnswerEntry[] = []
  for (const raw of parts) {
    const body = raw.trim().replace(/^\d{1,2}\s*[.、．]\s*/, '')
    if (!body) continue
    // 按中文逗号切块；首块（不含全角冒号）= 地点名，其余按 "键：值" 解析
    const segments = body.split(/[，,]/).map((s) => s.trim()).filter(Boolean)
    if (!segments.length) continue
    let name = segments[0]
    const fields: Array<[string, string]> = []
    for (const seg of segments.slice(1)) {
      const idx = seg.indexOf('：')
      if (idx > 0) {
        fields.push([seg.slice(0, idx).trim(), seg.slice(idx + 1).trim()])
      } else if (fields.length) {
        // 没有冒号的块 = 上一个值被逗号切断的延续（如地址里含逗号）
        fields[fields.length - 1][1] += `，${seg}`
      }
    }
    // 首块也可能是 "地点名：X" 形态
    const nameColon = name.indexOf('：')
    if (nameColon > 0 && /地点|名称/.test(name.slice(0, nameColon))) name = name.slice(nameColon + 1).trim()
    if (!name) continue

    let addr: string | null = null
    const chips: string[] = []
    for (const [k, v] of fields) {
      if (!v || EMPTY_VALUE_RE.test(v)) continue
      if (/地址/.test(k)) addr = v
      else if (/费用/.test(k)) chips.push(v.includes('免费') ? '💰 免费' : `💰 ${v}`)
      else if (/过夜|露营/.test(k)) chips.push(/允许|可以|可/.test(v) && !/不可|不允许|禁止/.test(v) ? '🌙 可过夜' : `🌙 ${v}`)
      else if (/停车/.test(k)) chips.push(`🅿️ ${v}`)
      else if (/厕所/.test(k)) chips.push(`🚻 ${v}`)
      else if (/水源/.test(k)) chips.push(`💧 ${v}`)
      else if (/日期|时间/.test(k)) chips.push(`📅 ${v}`)
      else chips.push(`${k} ${v}`)
    }
    entries.push({ name, addr, chips })
  }
  if (entries.length < 2) return null // 只解析出 0-1 条不值得切卡，回退纯文本
  return { preamble, entries }
}

/** 把信源按平台聚合成 [{emoji,label,count}]，按数量降序 */
function platformSummary(sources: ReturnType<typeof factSources>) {
  const counts = new Map<string, number>()
  for (const s of sources) {
    const key = detectPlatform(s.domain)
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({
      key,
      emoji: PLATFORM_EMOJI[key] || '🌐',
      label: PLATFORM_META[key as keyof typeof PLATFORM_META]?.label || '网页',
      count,
    }))
}

export interface AnswerPanelProps {
  answer: AISearchResponse['answer'] | null | undefined
  warningCode: string | null
  /** 通过分类/设施筛选后展示在地图上的 AI 候选数 */
  filteredAiCandidatesCount: number
  /** 未入图的"线索"数（unmapped_candidates）*/
  unmappedCount: number
}

export function AnswerPanel({ answer, warningCode, filteredAiCandidatesCount, unmappedCount }: AnswerPanelProps) {
  if (!answer?.text) return null
  if (warningCode && ['network_error', 'empty_answer', 'no_traceable_sources'].includes(warningCode)) {
    return null
  }

  const sources = factSources(answer.sources)
  const isTimeout = warningCode === 'extract_timeout'
  // H5：剥掉正文里的"来源链接：http://…"裸 URL 噪声（链接已由下方信源 chip 承载）。
  // weapp 保持原文不动（本组件双端共享；TARO_ENV 是编译期常量，weapp 包不含此分支）。
  const displayText = process.env.TARO_ENV === 'h5' ? stripAnswerLinkNoise(answer.text) : answer.text
  // H5：尝试把"编号流水账"切成结构化条目卡；解析不出（叙事体/流式早期）回退纯文本
  const parsed = process.env.TARO_ENV === 'h5' ? parseAnswerEntries(displayText) : null

  return (
    <View className={`answer-panel ${isTimeout ? 'incomplete' : ''}`}>
      <View className='answer-title-row'>
        <Text className='answer-title'>{process.env.TARO_ENV === 'h5' ? '🔥 AI 营地情报' : 'AI 提炼结果'}</Text>
        {isTimeout && <Text className='answer-incomplete-badge'>⚠ 抽取未完成</Text>}
      </View>
      <View className='ai-gen-chip-row'>
        <AiGeneratedTag />
      </View>
      {/* H5：信源平台概览 chips（📕 小红书 ·N），demo2 样式；逐条可点的信源 chip 仍在下方 */}
      {process.env.TARO_ENV === 'h5' && sources.length > 0 && (
        <View className='platform-summary-row'>
          {platformSummary(sources).map((p) => (
            <Text key={p.key} className='platform-summary-chip'>{p.emoji} {p.label} {p.count}</Text>
          ))}
        </View>
      )}
      {process.env.TARO_ENV === 'h5' && parsed ? (
        <View className='answer-entries'>
          {!!parsed.preamble && <Text className='answer-text'>{parsed.preamble}</Text>}
          {parsed.entries.map((entry, i) => (
            <View key={`${entry.name}-${i}`} className='answer-entry'>
              <Text className='answer-entry-name'>{entry.name}</Text>
              {!!entry.addr && <Text className='answer-entry-addr'>📍 {entry.addr}</Text>}
              {entry.chips.length > 0 && (
                <View className='answer-entry-chips'>
                  {entry.chips.map((chip) => (
                    <Text key={chip} className='answer-entry-chip'>{chip}</Text>
                  ))}
                </View>
              )}
            </View>
          ))}
        </View>
      ) : (
        <Text className='answer-text'>{displayText}</Text>
      )}
      <View className='answer-meta'>
        <Text>点位 {filteredAiCandidatesCount}</Text>
        <Text>线索 {unmappedCount}</Text>
        <Text>来源 {sources.length}</Text>
      </View>
      {!!sources.length && (
        <ScrollView className='source-strip' scrollX>
          {sources.map((source, index) => (
            <View
              key={sourceUrl(source) || index}
              className='source-chip'
              onClick={() => openExternalUrl(sourceUrl(source))}
            >
              [{index + 1}] {source.domain || '来源'} · {formatDate(sourceDate(source))}
            </View>
          ))}
        </ScrollView>
      )}
      {isTimeout && (
        <Text className='answer-incomplete-hint'>
          ⓘ 上面文字是 AI 联网找到的内容，但还没整理成可入图的结构化点位。可以点信源 chip 自己查看，或稍后重试同一搜索。
        </Text>
      )}
    </View>
  )
}
