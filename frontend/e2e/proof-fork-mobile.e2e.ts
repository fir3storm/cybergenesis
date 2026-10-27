import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const API = 'http://localhost:8000'

async function latestRun(request: APIRequestContext): Promise<{ id: string; state: string }> {
  const runs = await (await request.get(`${API}/api/experiments`)).json() as { id: string; state: string }[]
  return runs[0]
}

/** Run the demo from the UI and approve every human-approval gate until THIS run finishes. */
async function runDemoToCompletion(page: Page, request: APIRequestContext): Promise<string> {
  await request.post(`${API}/api/demo/reset`)
  const prevId = (await latestRun(request))?.id
  await page.goto('/')
  await page.getByRole('button', { name: /Run Autonomous Defense Demo/ }).click()
  await expect(page.getByText('LIVE EVENT TIMELINE')).toBeVisible()
  for (let i = 0; i < 200; i++) {
    const run = await latestRun(request)
    if (run?.id !== prevId && (run.state === 'COMPLETED' || run.state === 'FAILED')) return run.id
    const approve = page.getByRole('button', { name: 'Approve defense' })
    if (await approve.isVisible().catch(() => false)) await approve.click()
    await page.waitForTimeout(1000)
  }
  throw new Error('demo run did not finish in time')
}

test('proof certificate downloads, then a counterfactual fork compares against the original', async ({ page, request }) => {
  const runId = await runDemoToCompletion(page, request)
  await page.getByRole('button', { name: /PROOF/ }).hover()
  await page.getByRole('menuitem', { name: 'Verification Lab' }).click()
  await expect(page.getByText(/^(PASS|FAIL)$/).first()).toBeVisible({ timeout: 60_000 })

  // proof-carrying defense: only offered on a PASS
  const verdict = await (await request.get(`${API}/api/experiments/${runId}/results`)).json() as { verification: { outcome: string } }
  test.skip(verdict.verification.outcome !== 'PASS', 'run did not PASS; proof is only offered for PASS runs')
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download proof' }).click(),
  ])
  expect(download.suggestedFilename()).toBe(`certificate-${runId}.json`)
  await expect(page.getByLabel('Proof certificate').getByText(/Signature \(HMAC-SHA256\)/)).toBeVisible()
  await expect(page.getByLabel('Proof certificate').getByText(/Event hash chain/)).toBeVisible()
  await expect(page.getByLabel('Proof certificate').getByText(/Campaigns replayed/)).toBeVisible()
  await expect(page.getByLabel('Proof certificate').getByText(/Verify locally: python scripts\/verify_cert\.py/)).toBeVisible()
  // the downloaded file itself — not just the API — carries signature + unreachable_proof
  const dlPath = await download.path()
  expect(dlPath).toBeTruthy()
  const { readFileSync } = await import('node:fs')
  const cert = JSON.parse(readFileSync(dlPath as string, 'utf-8')) as {
    signature: string; event_hash_chain: string; campaigns: { unreachable_proof: { target_reachable: boolean } }[]
  }
  expect(cert.signature).toMatch(/^[0-9a-f]{64}$/)
  expect(cert.event_hash_chain).toMatch(/^[0-9a-f]{64}$/)
  expect(cert.campaigns.length).toBeGreaterThan(0)
  expect(cert.campaigns.at(-1)?.unreachable_proof.target_reachable).toBe(false)

  // time machine: fork with an alternative candidate, original stays unchanged
  const before = await (await request.get(`${API}/api/experiments/${runId}/results`)).json() as { verification: unknown }
  const tm = page.getByLabel('Counterfactual time machine')
  await expect(tm).toBeVisible()
  await tm.getByRole('button', { name: /^⑂ / }).first().click()
  await expect(tm.getByText('Red-team rounds')).toBeVisible({ timeout: 30_000 })
  await expect(tm.getByRole('cell', { name: 'Verdict', exact: true })).toBeVisible()
  await expect(tm.getByText('Δ (fork − original)')).toBeVisible()
  await expect(tm.getByText('Original timeline')).toBeVisible()
  await expect(tm.getByText('Fork timeline')).toBeVisible()
  await expect(tm.getByText('Original twin (after defense)')).toBeVisible()
  await expect(tm.getByText('Fork twin (after defense)')).toBeVisible()
  await expect(tm.getByRole('button', { name: 'Open fork run' })).toBeVisible()
  const after = await (await request.get(`${API}/api/experiments/${runId}/results`)).json() as { verification: unknown }
  expect(after.verification).toEqual(before.verification)
})

test('mobile approval page approves once; the token is single-use', async ({ page, request }) => {
  await request.post(`${API}/api/demo/reset`)
  const created = await (await request.post(`${API}/api/experiments`, { data: { scenario_id: 'ransomware_activity', seed: 42 } })).json() as { id: string }
  await request.post(`${API}/api/experiments/${created.id}/run`)
  let info: { pending: boolean; mobile_url?: string } = { pending: false }
  for (let i = 0; i < 150 && !info.pending; i++) {
    info = await (await request.get(`${API}/api/experiments/${created.id}/approval`)).json()
    if (!info.pending) await page.waitForTimeout(1000)
  }
  test.skip(!info.pending, 'no human-approval gate fired (HUMAN_APPROVAL_ENABLED/auto-approve settings)')
  const url = new URL(info.mobile_url as string)
  const token = url.searchParams.get('t') as string
  // the phone would use the LAN address; the test reaches the same backend on localhost
  await page.goto(`${API}${url.pathname}?t=${token}`)
  await expect(page.getByRole('button', { name: 'Approve defense' })).toBeVisible()
  await page.getByRole('button', { name: 'Approve defense' }).click()
  await expect(page.getByText(/Recorded/)).toBeVisible()

  const reuse = await request.post(`${API}/api/m/approve/${created.id}`, { data: { t: token, approved: true } })
  expect(reuse.status()).toBe(403)
  // resolve any later round so the run finishes cleanly
  for (let i = 0; i < 150; i++) {
    const run = (await (await request.get(`${API}/api/experiments`)).json() as { id: string; state: string }[]).find((r) => r.id === created.id)
    if (run && (run.state === 'COMPLETED' || run.state === 'FAILED')) break
    await request.post(`${API}/api/experiments/${created.id}/approve`, { data: { approved: true } }).catch(() => undefined)
    await page.waitForTimeout(1000)
  }
  const events = await (await request.get(`${API}/api/experiments/${created.id}/events`)).json() as { event_type: string }[]
  expect(events.some((e) => e.event_type === 'approval_mobile')).toBe(true)
})
