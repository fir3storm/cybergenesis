import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from './api'

beforeEach(() => sessionStorage.clear())
afterEach(() => vi.unstubAllGlobals())

it('bootstraps a local operator token before the first mutation', async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/api/settings/providers')) return new Response(JSON.stringify({ admin_token: 'local-token' }))
    const token = new Headers(init?.headers).get('x-admin-token')
    return token === 'local-token' ? new Response(JSON.stringify({ reset: true })) : new Response('', { status: 403 })
  })
  vi.stubGlobal('fetch', fetcher)
  await expect(api.reset()).resolves.toEqual({ reset: true })
  expect(sessionStorage.getItem('cybergenesis_admin_token')).toBe('local-token')
})

it('uses an operator-entered token without requesting a replacement', async () => {
  sessionStorage.setItem('cybergenesis_admin_token', 'hosted-token')
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.endsWith('/api/settings/providers')) throw new Error('must not replace hosted token')
    return new Headers(init?.headers).get('x-admin-token') === 'hosted-token'
      ? new Response(JSON.stringify({ reset: true })) : new Response('', { status: 403 })
  })
  await expect(api.reset()).resolves.toEqual({ reset: true })
})

it('tells a hosted viewer how to unlock operator controls', async () => {
  vi.stubGlobal('fetch', async (url: string) => url.endsWith('/api/settings/providers')
    ? new Response(JSON.stringify({ providers: [] })) : new Response('', { status: 403 }))
  await expect(api.reset()).rejects.toThrow(/Settings/)
})
