import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PreflightPanel } from './preflight'
import { api } from '../services/api'

vi.mock('../services/api', () => ({ api: { preflight: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('shows FAIL banner and the regression path', async () => {
  vi.mocked(api.preflight).mockResolvedValue({
    verdict: 'FAIL', change_ops: [{ op: 'add_link', src: 'relay', dst: 'database' }], twin_sha256_before: 'x', generated_at: 'now',
    results: [{ scenario_id: 'lateral_movement', scenario_name: 'Lat', source: 'web-server', target: 'database', status: 'REGRESSION', baseline_reachable: true, after_reachable: true, baseline_paths: [['web-server', 'app-server', 'database']], after_paths: [['web-server', 'relay', 'database']], new_paths: [['web-server', 'relay', 'database']], min_cut_before: 1, min_cut_after: 1 }],
  } as never)
  render(<PreflightPanel />)
  fireEvent.click(screen.getByText('Run preflight'))
  await waitFor(() => expect(screen.getByText(/FAIL — regression detected/)).toBeTruthy())
  expect(screen.getAllByText(/web-server → relay → database/).length).toBeGreaterThan(0)
  expect(vi.mocked(api.preflight)).toHaveBeenCalled()
})

it('shows PASS banner for a safe change', async () => {
  vi.mocked(api.preflight).mockResolvedValue({
    verdict: 'PASS', change_ops: [], twin_sha256_before: 'x', generated_at: 'now',
    results: [{ scenario_id: 'lateral_movement', scenario_name: 'Lat', source: 'web-server', target: 'database', status: 'STILL_EXPOSED', baseline_reachable: true, after_reachable: true, baseline_paths: [], after_paths: [], new_paths: [], min_cut_before: 1, min_cut_after: 1 }],
  } as never)
  render(<PreflightPanel />)
  fireEvent.click(screen.getByText('Run preflight'))
  await waitFor(() => expect(screen.getByText(/PASS — no regression/)).toBeTruthy())
})
