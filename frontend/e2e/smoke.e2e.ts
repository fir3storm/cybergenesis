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
  await page.getByRole('button', { name: 'Verification Lab' }).click()
  await expect(page.getByText(/^(PASS|FAIL)$/).first()).toBeVisible({ timeout: 60_000 })
})
