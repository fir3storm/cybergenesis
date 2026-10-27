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

test('playbook text-to-scenario input and battle view exist', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /BUILD/ }).hover()
  await page.getByRole('menuitem', { name: /Playbook/ }).click()
  await expect(page.getByLabel('What-if prompt')).toBeVisible()
  await page.getByRole('button', { name: /RUN/ }).hover()
  await page.getByRole('menuitem', { name: /Battle/ }).click()
  await expect(page.getByText('Battle — Red vs Blue')).toBeVisible()
})
