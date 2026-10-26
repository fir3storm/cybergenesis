// Captures the 6 submission screenshots with headless Edge (WebGL via SwiftShader).
// Requires backend :8000 and frontend :5173 running. Usage: node scripts/screenshots.mjs
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const OUT = fileURLToPath(new URL('../../docs/screenshots/', import.meta.url))
mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const shot = async (name) => { await page.screenshot({ path: `${OUT}${name}` }); console.log(name) }

await page.goto('http://localhost:5173', { waitUntil: 'networkidle' })
await page.getByText(/LIVE META AI|OFFLINE SIMULATION/).first().waitFor({ timeout: 20000 })
await page.waitForTimeout(3500) // let the 3D twin render
await shot('01-welcome.png')

await page.getByRole('button', { name: 'Living Twin' }).click()
await page.waitForTimeout(2500)
await shot('02-living-twin.png')

await page.getByRole('button', { name: 'Open Experiment Console' }).click()
await page.getByRole('button', { name: 'RUN EXPERIMENT' }).click()
await page.getByText('LIVE EVENT TIMELINE').waitFor()
await page.waitForTimeout(6000) // mid-attack: red path + telemetry streaming
await shot('03-experiment-running.png')
await page.getByText('AGENT DECISIONS THIS RUN').waitFor()
await page.waitForFunction(() => document.body.innerText.includes('Effectiveness'), null, { timeout: 90000 })

await page.getByRole('button', { name: 'Agents' }).click()
await page.getByText('click to inspect').first().waitFor()
await page.getByText('Defense Strategist').first().click()
await page.waitForTimeout(700)
await shot('04-agents.png')

await page.getByRole('button', { name: 'Verification Lab' }).click()
await page.waitForTimeout(800)
await shot('05-verification-lab.png')

await page.getByRole('button', { name: 'Evidence' }).click()
await page.getByRole('button', { name: /Load evidence/ }).click()
await page.waitForTimeout(800)
await shot('06-evidence.png')

await browser.close()
console.log('done ->', OUT)
