/**
 * spec-017 / B 方案：二维码 modal 单例控制器
 *
 * 为什么用 singleton 而不是 Context：避免改 openExternalUrl 的所有调用方
 * （SourceLeadCard / AnswerPanel / PlaceDetailDrawer 等多处都在用）。
 *
 * 使用：
 *  - 顶层组件（index.tsx）用 useState 管 qrUrl、useEffect 调 registerQRModalShowFn 把 setQrUrl 注册进来
 *  - 任意组件调 showQRCodeModal(url) 弹出二维码
 */

type ShowFn = (url: string) => void

let _showFn: ShowFn | null = null

export function registerQRModalShowFn(fn: ShowFn | null): void {
  _showFn = fn
}

export function showQRCodeModal(url: string): boolean {
  if (_showFn) {
    _showFn(url)
    return true
  }
  // eslint-disable-next-line no-console
  console.warn('[qr-modal] showQRCodeModal 调用时控制器未注册——降级到剪贴板复制')
  return false
}
