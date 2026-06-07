/**
 * P2-4-D: 顶部搜索框 + AI 搜索按钮 + 搜索期间的进度卡（含 SSE 阶段文案 + 进度条）。
 *
 * 受控组件（query/searching/progress 由父组件 IndexPage 持有），方便和 runSearch / state 协同。
 */
import { Button, Input, Text, View } from '@tarojs/components'

export interface SearchBarProps {
  query: string
  searching: boolean
  /** SSE pipeline 进度文案，形如 "正在搜索网页…（5s）" */
  progress: string
  onQueryChange: (v: string) => void
  onSearch: () => void
}

/** 从进度文案末尾的 "（Ns）" 提取秒数；找不到返 0 */
function parseElapsedSeconds(progress: string): number {
  const match = progress.match(/（(\d+)s）/)
  return match ? parseInt(match[1], 10) || 0 : 0
}

export function SearchBar({ query, searching, progress, onQueryChange, onSearch }: SearchBarProps) {
  // 进度条按 90 秒上限算百分比（搜+抽+地理编码总预算）
  const progressPct = Math.min(100, Math.round((parseElapsedSeconds(progress) / 90) * 100))

  return (
    <>
      <View className='search-row'>
        <View className='search-shell'>
          <Text className='search-symbol'>⌕</Text>
          <Input
            className='search-input'
            value={query}
            placeholder='输入地点或需求，例如：莫干山自驾露营'
            confirmType='search'
            onInput={(event) => onQueryChange(event.detail.value)}
            onConfirm={onSearch}
          />
        </View>
        <Button className='primary-btn search-btn' loading={searching} onClick={onSearch}>
          AI搜索
        </Button>
      </View>
      {searching && (
        <View className='search-progress-card'>
          <View className='progress-text-row'>
            <Text className='progress-stage'>{progress || '正在联网检索…'}</Text>
          </View>
          <View className='progress-bar-track'>
            <View className='progress-bar-fill' style={{ width: `${progressPct}%` }} />
          </View>
          <Text className='progress-hint'>预计 30-90 秒；AI 联网 + 抽取 + 地理编码 三步</Text>
        </View>
      )}
    </>
  )
}
