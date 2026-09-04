import { readFileSync } from 'node:fs'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, chatSessionId, getToken, saveSession } from './api'

function createStorage(): Storage {
  const values = new Map<string, string>()

  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => values.delete(key),
    setItem: (key: string, value: string) => values.set(key, value),
  } as Storage
}

describe('session handling', () => {
  let session: Storage
  let local: Storage
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    session = createStorage()
    local = createStorage()
    fetchMock = vi.fn()
    vi.stubGlobal('sessionStorage', session)
    vi.stubGlobal('localStorage', local)
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps the bearer token out of persistent local storage', () => {
    saveSession('token-alice', 'alice')

    expect(getToken()).toBe('token-alice')
    expect(session.getItem('soa_token')).toBe('token-alice')
    expect(local.getItem('soa_token')).toBeNull()
  })

  it('uses a separate chat session for each signed-in user', () => {
    saveSession('token-alice', 'alice')
    const aliceSession = chatSessionId()

    saveSession('token-bob', 'bob')
    const bobSession = chatSessionId()

    expect(bobSession).not.toBe(aliceSession)
  })

  it('does not attach an existing bearer token to a login request', async () => {
    saveSession('old-token', 'alice')
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ token: 'new-token' }), { status: 200 }))

    await api.login('bob', 'password')

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(init.headers).get('Authorization')).toBeNull()
  })
})

describe('page security policy', () => {
  it('declares a restrictive content security policy', () => {
    const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')

    expect(html).toContain('Content-Security-Policy')
    expect(html).toContain("default-src 'self'")
    expect(html).toContain("object-src 'none'")
  })
})

describe('login boundary', () => {
  it('renders the login route outside the control-panel shell', () => {
    const app = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')

    expect(app).toContain('<LoginView v-if="route.name === \'login\'" />')
    expect(app).toContain('<div v-else class="shell">')
  })
})
