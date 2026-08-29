import { reactive } from 'vue'

export type ToastKind = 'ok' | 'err' | 'info'

export interface ToastItem {
  id: number
  kind: ToastKind
  text: string
}

export const toastState = reactive<{ items: ToastItem[] }>({ items: [] })

let seq = 0

export function toast(text: string, kind: ToastKind = 'info'): void {
  const id = ++seq
  toastState.items.push({ id, kind, text })
  window.setTimeout(() => {
    const i = toastState.items.findIndex((t) => t.id === id)
    if (i >= 0) toastState.items.splice(i, 1)
  }, 4500)
}