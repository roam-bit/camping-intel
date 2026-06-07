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
import { factSources, formatDate, openExternalUrl, sourceDate, sourceUrl } from '../utils/place-helpers'
import { AiGeneratedTag } from './AiContentLabels'

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

  return (
    <View className={`answer-panel ${isTimeout ? 'incomplete' : ''}`}>
      <View className='answer-title-row'>
        <Text className='answer-title'>AI 提炼结果</Text>
        {isTimeout && <Text className='answer-incomplete-badge'>⚠ 抽取未完成</Text>}
      </View>
      <View className='ai-gen-chip-row'>
        <AiGeneratedTag />
      </View>
      <Text className='answer-text'>{answer.text}</Text>
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
