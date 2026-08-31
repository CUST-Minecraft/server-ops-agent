export function fmtClock(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export function fmtDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${fmtDate(d)} ${fmtClock(d)}`
}

export function relTime(iso: string, now: Date = new Date()): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = Math.max(0, now.getTime() - t)
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  return `${d} 天前`
}

export function fmtCountdown(expiresIso: string, now: Date = new Date()): string {
  const t = new Date(expiresIso).getTime()
  if (Number.isNaN(t)) return expiresIso
  const remain = t - now.getTime()
  if (remain <= 0) return '已过期'
  const sec = Math.floor(remain / 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  if (sec >= 3600) return `剩余 ${Math.floor(sec / 3600)}:${p(Math.floor((sec % 3600) / 60))}:${p(sec % 60)}`
  return `剩余 ${p(Math.floor(sec / 60))}:${p(sec % 60)}`
}

export function pctColor(pct: number): string {
  if (pct >= 85) return 'var(--red)'
  if (pct >= 70) return 'var(--amber)'
  return 'var(--green)'
}