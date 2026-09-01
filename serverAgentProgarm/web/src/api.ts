export interface MetricSnapshot {
  id: number
  collected_at: string
  cpu_used_pct: number
  load_1m: number
  load_5m: number
  load_15m: number
  mem_used_pct: number
  mem_available_mb: number
  disk_used_pct: number
  services_status: Record<string, string>
}

export interface Incident {
  id: number
  kind: string
  severity: string
  status: string
  title: string
  opened_at: string
  resolved_at: string | null
}

export interface ApprovalRequest {
  id: number
  tool: string
  args: unknown
  reason: string
  status: string
  created_at: string
  expires_at: string
}

export interface StatusPayload {
  snap: MetricSnapshot | null
  latest: Incident | null
  pending: number
}

export interface IncidentsPayload {
  incidents: Incident[]
}

export interface ApprovalsPayload {
  reqs: ApprovalRequest[]
}

export interface ActionPayload {
  ok: boolean
  message: string
}

/* —— 单子详情：每次调查的轨迹 / 结论 / 建议 —— */
export interface TrailStep {
  step: number
  tool: string
  args: Record<string, unknown>
  status: string
  summary: string
}

export interface SuggestedAction {
  description: string
  command: string
  expected_effect: string
  risk_note?: string
}

export interface Conclusion {
  root_cause: string
  evidence?: string[]
  recommended_runbook: string | null
  confidence?: string
  trail?: TrailStep[]
  suggested_action?: SuggestedAction | null
}

export interface InvestigationEntry {
  attempt: number
  at: string
  conclusion: Conclusion
}

export interface IncidentDetailPayload {
  inc: Incident
  history: InvestigationEntry[]
  notes: string[]
}

/* —— 认证：day15 前端预留（后端鉴权时启用） —— */
export interface AuthPayload {
  token: string
}

const TOKEN_KEY = 'soa_token'
const USER_KEY = 'soa_user'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUsername(): string | null {
  return localStorage.getItem(USER_KEY)
}

export function saveSession(token: string, username: string): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, username)
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

interface AuthEventDetail {
  msg: string
}
export const AUTH_EVENT = 'soa-auth'
function emitAuth(msg: string): void {
  window.dispatchEvent(new CustomEvent<AuthEventDetail>(AUTH_EVENT, { detail: { msg } }))
}

function authHeaders(extra?: Record<string, string>): Headers {
  const headers = new Headers(extra)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

function handle401(path: string): void {
  const had = getToken()
  clearSession()
  emitAuth(had ? `登录已过期，请重新登录（${path}）` : `需要登录才能访问（${path}）`)
}

async function bodyDetail(res: Response): Promise<string | null> {
  const body = await res.json().catch(() => null)
  return body?.detail ?? null
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (res.status === 401) {
    handle401(path)
    throw new Error((await bodyDetail(res)) ?? '未登录或登录已过期')
  }
  if (!res.ok) throw new Error((await bodyDetail(res)) ?? `HTTP ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401) {
    handle401(path)
    throw new Error((await bodyDetail(res)) ?? '未登录或登录已过期')
  }
  if (!res.ok) throw new Error((await bodyDetail(res)) ?? `HTTP ${res.status}`)
  return res.json() as Promise<T>
}

/* —— Web Chat（Day 14）：SSE 流式 + 对话历史落库 —— */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatHistoryPayload {
  messages: ChatMessage[]
}

const SESSION_KEY = 'soa_chat_session'

export function chatSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

export function chatHistory(): Promise<ChatHistoryPayload> {
  return get<ChatHistoryPayload>(
    `/api/chat/messages?session_id=${encodeURIComponent(chatSessionId())}`,
  )
}

export interface ChatStreamHandlers {
  onDelta: (text: string) => void
  onDone: () => void
  onError: (message: string) => void
}

/* SSE 流式问答：data: {content} 逐块推进，遇 done / [DONE] / 流关闭即结束。 */
export async function chatStream(
  messages: ChatMessage[],
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${BASE}/api/chat/stream`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ session_id: chatSessionId(), messages }),
      signal,
    })
  } catch (e) {
    if ((e as Error).name !== 'AbortError') handlers.onError(e instanceof Error ? e.message : String(e))
    return
  }
  if (res.status === 401) {
    handle401('/api/chat/stream')
    handlers.onError('未登录或登录已过期')
    return
  }
  if (!res.ok) {
    handlers.onError((await bodyDetail(res)) ?? `HTTP ${res.status}`)
    return
  }
  const reader = res.body?.getReader()
  if (!reader) {
    handlers.onError('响应流不可读')
    return
  }
  const decoder = new TextDecoder()
  let buf = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let sep: number
      while ((sep = buf.indexOf('\n\n')) >= 0) {
        const raw = buf.slice(0, sep)
        buf = buf.slice(sep + 2)
        const line = raw.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        const payload = line.slice(5).trim()
        if (!payload || payload === '[DONE]') {
          handlers.onDone()
          continue
        }
        try {
          const obj = JSON.parse(payload)
          if (typeof obj.content === 'string') handlers.onDelta(obj.content)
          else if (typeof obj.error === 'string') handlers.onError(obj.error)
          else if (obj.done) handlers.onDone()
        } catch {
          handlers.onDelta(payload)
        }
      }
    }
    handlers.onDone()
  } catch (e) {
    if ((e as Error).name !== 'AbortError') handlers.onError(e instanceof Error ? e.message : String(e))
  } finally {
    reader.releaseLock()
  }
}

export const api = {
  status: () => get<StatusPayload>('/api/status'),
  incidents: () => get<IncidentsPayload>('/api/incidents'),
  incident: (id: number) => get<IncidentDetailPayload>(`/api/incidents/${id}`),
  approvals: () => get<ApprovalsPayload>('/api/approvals'),
  approve: (id: number) => post<ActionPayload>(`/api/approvals/${id}/approve`),
  reject: (id: number) => post<ActionPayload>(`/api/approvals/${id}/reject`),
  /* day15 预留：后端实现 /api/auth/login + /api/auth/logout 后启用 */
  login: (username: string, password: string) =>
    post<AuthPayload>('/api/auth/login', { username, password }),
  logout: () => post<{ ok: boolean }>('/api/auth/logout'),
}