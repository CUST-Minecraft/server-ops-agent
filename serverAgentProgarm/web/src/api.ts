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

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST' })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  status: () => get<StatusPayload>('/api/status'),
  incidents: () => get<IncidentsPayload>('/api/incidents'),
  approvals: () => get<ApprovalsPayload>('/api/approvals'),
  approve: (id: number) => post<ActionPayload>(`/api/approvals/${id}/approve`),
  reject: (id: number) => post<ActionPayload>(`/api/approvals/${id}/reject`),
}