import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'

test('arena: play a learned match, spectate rounds, winner proof offered', async ({ page, request }) => {
  // backend learns from a first match played over the API
  const first = await request.post(`${API}/api/arena/matches`, { data: { scenario_id: 'red_vs_blue_battle', mode: 'learned' } })
  expect(first.ok()).toBeTruthy()
  const firstBody = await first.json() as { winner: string; memory: { matches: number } }
  expect(['red', 'blue']).toContain(firstBody.winner)
  expect(firstBody.memory.matches).toBeGreaterThanOrEqual(1)

  await page.goto('/')
  await page.getByRole('button', { name: /RUN/ }).hover()
  await page.getByRole('menuitem', { name: 'Arena' }).click()
  await expect(page.getByRole('heading', { name: /Arena/ })).toBeVisible()
  await expect(page.getByLabel('Arena league')).toBeVisible()

  // second match from the UI, learning-only so it is deterministic in any mode
  await page.getByLabel('Strategy').selectOption('learned')
  await page.getByRole('button', { name: 'Play match' }).click()
  await expect(page.getByText(/^(RED WINS|BLUE WINS)/)).toBeVisible({ timeout: 90_000 })
  await expect(page.getByLabel('Red rounds')).toContainText('Round 1')
  await expect(page.getByLabel('Blue rounds')).toContainText('Round 1')
  await expect(page.getByLabel('What the arena learned')).toContainText('Blue defenses')
  await expect(page.getByRole('button', { name: 'Download winner proof' })).toBeVisible()

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download winner proof' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/^arena-certificate-.+\.json$/)
  const dlPath = await download.path()
  const { readFileSync } = await import('node:fs')
  const cert = JSON.parse(readFileSync(dlPath as string, 'utf-8')) as { kind: string; winner: string; signature: string }
  expect(cert.kind).toBe('arena_match')
  expect(cert.signature).toMatch(/^[0-9a-f]{64}$/)

  const league = await (await request.get(`${API}/api/arena/league`)).json() as { matches: number; red_wins: number; blue_wins: number }
  expect(league.red_wins + league.blue_wins).toBe(league.matches)
  expect(league.matches).toBeGreaterThanOrEqual(2)
})
