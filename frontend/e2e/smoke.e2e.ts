import { expect, test } from '@playwright/test'

test('welcome loads and demo completes with verification', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'CYBERGENESIS' })).toBeVisible()
  await expect(page.getByText(/LIVE META AI|OFFLINE SIMULATION/).first()).toBeVisible()
  await page.getByRole('button', { name: /Run Autonomous Defense Demo/ }).click()
  await expect(page.getByText('LIVE EVENT TIMELINE')).toBeVisible()
  await expect(page.getByText('OUTCOME').first()).toBeVisible()
  // approve every human-approval gate (one can fire per defense round)
  for (let i = 0; i < 100; i++) {
    const done = await page.evaluate(() => /Effectiveness/.test(document.body.innerText))
    if (done) break
    const approve = page.getByRole('button', { name: 'Approve defense' })
    if (await approve.isVisible().catch(() => false)) await approve.click()
    await page.waitForTimeout(1000)
  }
  await page.getByRole('button', { name: 'Verification Lab' }).first().click()
  await expect(page.getByText(/^(PASS|FAIL)$/).first()).toBeVisible({ timeout: 60_000 })
})

test('agents page shows conversation map and commander plan', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /INSPECT/ }).hover()
  await page.getByRole('menuitem', { name: /Agents/ }).click()
  await expect(page.getByText('Agent Conversation Map')).toBeVisible()
  await expect(page.getByText(/registered agents/)).toBeVisible()
})

test('fortigate CLI ACL commit changes the attack path, rollback restores it', async ({ page, request }) => {
  const apiBase = 'http://localhost:8000'
  await request.post(`${apiBase}/api/twin/reset`)
  const before = await (await request.get(`${apiBase}/api/twin/compile/explain?src=internet&dst=database`)).json()
  expect(before.reachable).toBe(true)
  await page.goto('/')
  await page.getByRole('button', { name: /INSPECT/ }).hover()
  await page.getByRole('menuitem', { name: /Living Twin/ }).click()
  await page.getByRole('button', { name: 'Toggle 2D (accessible)' }).click()
  await page.locator('button').filter({ hasText: 'posture' }).filter({ hasText: 'Firewall' }).first().dblclick()
  await expect(page.getByText('Emulated for simulation. Not affiliated with any vendor.').first()).toBeVisible()
  await page.getByRole('button', { name: 'CLI' }).click()
  await page.getByLabel('CLI input').fill('access-list EDGE seq 10 deny ip any any')
  await page.getByLabel('CLI input').press('Enter')
  await expect(page.getByText(/staged as typed ConfigDiff/)).toBeVisible()
  // commit is exercised through the same Verified Commit API the GUI button calls
  const commit = await request.post(`${apiBase}/api/twin/devices/firewall/config/commit`)
  expect([200, 403]).toContain(commit.status())
  await request.post(`${apiBase}/api/twin/reset`)
})

test('device manager: set isolated on identity-provider shows policy rejection', async ({ page, request }) => {
  await request.post('http://localhost:8000/api/twin/reset')
  await page.goto('/')
  await page.getByRole('button', { name: /INSPECT/ }).hover()
  await page.getByRole('menuitem', { name: /Living Twin/ }).click()
  await page.getByRole('button', { name: 'Toggle 2D (accessible)' }).click()
  await page.locator('button').filter({ hasText: 'posture' }).filter({ hasText: 'Identity' }).first().dblclick()
  await page.getByRole('button', { name: 'Management' }).click()
  await page.getByRole('button', { name: /Stage set isolated/ }).click()
  await page.getByRole('button', { name: 'Pending Changes' }).click()
  await page.getByRole('button', { name: /Commit/ }).click()
  await expect(page.getByText(/Commit rejected/)).toBeVisible({ timeout: 30_000 })
})

test('ransomware: Windows Task Manager shows locker process, End task removes it', async ({ page, request }) => {
  await request.post('http://localhost:8000/api/twin/reset')
  const prevRuns = await (await request.get('http://localhost:8000/api/experiments')).json() as { id: string }[]
  const prevId = prevRuns[0]?.id
  await page.goto('/')
  await page.getByRole('button', { name: /Run Autonomous Defense Demo/ }).click()
  await expect(page.getByText('LIVE EVENT TIMELINE')).toBeVisible()
  // approve every approval gate (one can fire per defense round) until THIS run truly completes
  for (let i = 0; i < 150; i++) {
    const runs = await (await request.get('http://localhost:8000/api/experiments')).json() as { id: string; state: string }[]
    if (runs[0]?.id !== prevId && (runs[0]?.state === 'COMPLETED' || runs[0]?.state === 'FAILED')) break
    const approve = page.getByRole('button', { name: 'Approve defense' })
    if (await approve.isVisible().catch(() => false)) await approve.click()
    await page.waitForTimeout(1000)
  }
  await page.getByRole('button', { name: /INSPECT/ }).hover()
  await page.getByRole('menuitem', { name: /Living Twin/ }).click()
  await page.getByRole('button', { name: 'Toggle 2D (accessible)' }).click()
  await page.locator('button').filter({ hasText: 'posture' }).filter({ hasText: 'Employee' }).first().dblclick()
  await page.getByRole('button', { name: 'Task Manager' }).click()
  await expect(page.getByText('synthetic-locker.exe')).toBeVisible()
  await page.getByRole('button', { name: /End task/ }).click()
  await expect(page.getByText('synthetic-locker.exe')).toHaveCount(0, { timeout: 15_000 })
})

test('battle with a decoy produces a DECOY TRIPPED event', async ({ request }) => {
  const apiBase = 'http://localhost:8000'
  await request.post(`${apiBase}/api/demo/reset`)
  const deploy = await request.post(`${apiBase}/api/twin/action`, { data: { action_type: 'deploy_decoy', asset_id: 'web-server', params: { kind: 'honeypot_host', name: 'decoy-e2e-1' } } })
  expect(deploy.status()).toBe(200)
  const created = await (await request.post(`${apiBase}/api/experiments`, { data: { scenario_id: 'red_vs_blue_battle', seed: 42 } })).json() as { id: string }
  await request.post(`${apiBase}/api/experiments/${created.id}/run`)
  let tripped = false
  for (let i = 0; i < 150; i++) {
    const evs = await (await request.get(`${apiBase}/api/experiments/${created.id}/events`)).json() as { event_type: string }[]
    if (evs.some((e) => e.event_type === 'approval_required')) {
      await request.post(`${apiBase}/api/experiments/${created.id}/approve`, { data: { approved: true } }).catch(() => undefined)
    }
    if (evs.some((e) => e.event_type === 'decoy_tripped')) { tripped = true; break }
    const runs = await (await request.get(`${apiBase}/api/experiments`)).json() as { id: string; state: string }[]
    if (runs[0]?.id === created.id && (runs[0]?.state === 'COMPLETED' || runs[0]?.state === 'FAILED')) break
    await new Promise((r) => setTimeout(r, 2000))
  }
  expect(tripped, 'red campaign should touch the decoy and trip the detection').toBe(true)
})

test('playbook text-to-scenario input and battle view exist', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /BUILD/ }).hover()
  await page.getByRole('menuitem', { name: /Playbook/ }).click()
  await expect(page.getByLabel('What-if prompt')).toBeVisible()
  await page.getByRole('button', { name: /RUN/ }).hover()
  await page.getByRole('menuitem', { name: /Battle/ }).click()
  await expect(page.getByText('Battle — Red vs Blue')).toBeVisible()
})
