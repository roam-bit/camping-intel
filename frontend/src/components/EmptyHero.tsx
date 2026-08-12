/**
 * P2-4-C: 用户还没搜索时的"启动引导卡"。
 * 含 3 个示例 query 快捷按钮 + 右上 ✕ 关闭按钮。
 *
 * 状态由父组件 IndexPage 控制（heroDismissed），方便和 hasSearched / searching / mapError
 * 协同隐藏；这里只是一个"受控"展示组件。
 */
import { Button, Text, View } from '@tarojs/components'

const EXAMPLE_QUERIES = ['杭州周边免费露营地', '千岛湖驻车点', '莫干山附近营地']

export interface EmptyHeroProps {
  /** 用户点击示例 query 时回调（值是 query 字符串） */
  onQueryPick: (q: string) => void
  /** 用户点击右上角 ✕ 关闭卡片时回调 */
  onDismiss: () => void
}

export function EmptyHero({ onQueryPick, onDismiss }: EmptyHeroProps) {
  return (
    // 注意：不要给 .empty-hero 加内联 position——曾经的 style={{position:'relative'}}
    // 覆盖了 CSS 的 position:absolute，把整张卡顶出首屏（用户从未见过引导卡）。
    // ✕ 按钮的 absolute 定位以 .empty-hero（本身就是 absolute）为锚点，无需 relative。
    <View className='empty-hero'>
      <View
        className='empty-hero-close'
        onClick={onDismiss}
        style={{
          position: 'absolute',
          top: 10,
          right: 14,
          width: 28,
          height: 28,
          lineHeight: '26px',
          textAlign: 'center',
          borderRadius: 14,
          color: '#888',
          fontSize: 18,
          cursor: 'pointer',
          background: 'rgba(0,0,0,0.04)',
          userSelect: 'none',
        }}
      >
        ✕
      </View>
      <Text className='empty-hero-title'>搜索附近的露营点、驻车点、营地</Text>
      <Text className='empty-hero-sub'>AI 自动整理网友实测信源，你看完信源再决定是否前往</Text>
      <View className='empty-hero-chips'>
        {EXAMPLE_QUERIES.map((q) => (
          <Button key={q} className='hero-chip' onClick={() => onQueryPick(q)}>
            {q}
          </Button>
        ))}
      </View>
      <Text className='empty-hero-foot'>👇 也可以直接在上方搜索框输入</Text>
    </View>
  )
}
