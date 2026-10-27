// Records the 3-minute demo flow as a video (docs/demo.webm) with headless Edge.
// Requires backend :8000 (LIVE or OFFLINE) and frontend :5173 running.
// Usage: node scripts/record-demo.mjs
import { chromium } from 'playwright-core'
import { mkdirSync, renameSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const OUT = fileURLToPath(new URL('../../docs/', import.meta.url))
mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] })
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: OUT, size: { width: 1440, height: 900 } },
})
const page = await context.newPage()
const wait = (ms) => page.waitForTimeout(ms)

await page.goto('http://localhost:5173', { waitUntil: 'networkidle' })
await page.getByText(/LIVE META AI|OFFLINE SIMULATION/).first().waitFor({ timeout: 20000 })
await wait(5000) // 0:00-0:20 the living twin

await page.getByRole('button', { name: /Run Autonomous Defense Demo/ }).click()
await page.getByText('LIVE EVENT TIMELINE').waitFor()
await wait(9000) // attack progression + particles

for (let i = 0; i < 110; i++) { // approve human gates as they appear
  if (await page.evaluate(() => document.body.innerText.includes('Effectiveness'))) break
  const btn = page.getByRole('button', { name: 'Approve defense' })
  if (await btn.isVisible().catch(() => false)) await btn.click()
  await wait(1000)
}
await wait(3000)

await page.getByRole('button', { name: 'Verification Lab' }).first().click() // proof
await wait(6000)
await page.getByRole('button', { name: /INSPECT/ }).hover()
await page.getByRole('menuitem', { name: /Agents/ }).click() // agent reasoning
await wait(5000)
await page.getByRole('button', { name: /PROOF/ }).hover()
await page.getByRole('menuitem', { name: /Proof/ }).click() // benchmark table
await wait(5000)

await context.close() // flushes the video
await browser.close()
const webm = readdirSync(OUT).find((f) => f.endsWith('.webm'))
if (webm && webm !== 'demo.webm') renameSync(`${OUT}${webm}`, `${OUT}demo.webm`)
console.log('recorded -> docs/demo.webm')
