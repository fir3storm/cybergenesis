import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ArenaView } from './arena'
import { api } from '../services/api'

vi.mock('../stores/store', () => ({ useStore: () => ({ scenarios: [{ id: 'red_vs_blue_battle', name: 'Battle' }] }) }))
vi.mock('./twin', () => ({ Twin2D: () => <div>Twin</div> }))
vi.mock('../services/api', () => ({ api: {
  arenaEvaluation: vi.fn().mockResolvedValue({ available: false }), arenaLeague: vi.fn().mockResolvedValue(null), arenaMemory: vi.fn().mockResolvedValue(null),
  arenaMatches: vi.fn().mockResolvedValue([]), arenaPlay: vi.fn(),
} }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
const match = { id: 'm', rounds: [], rounds_played: 0, winner: 'blue', reason: 'blocked', total_disrupted: 0, final_twin: {}, mode: 'learned' }

it('runs the selected number of training battles and shows their outcomes', async () => {
  vi.mocked(api.arenaPlay).mockImplementation(async () => ({ ...match, id: String(vi.mocked(api.arenaPlay).mock.calls.length) }) as never)
  render(<ArenaView />)
  fireEvent.change(screen.getByLabelText('Training battles'), { target: { value: '3' } })
  fireEvent.click(screen.getByText('Train teams'))
  await screen.findByText(/3 \/ 3 battles completed/)
  expect(api.arenaPlay).toHaveBeenCalledTimes(3)
})

it('stops after the in-flight match without starting another', async () => {
  let resolve!: (value: never) => void
  vi.mocked(api.arenaPlay).mockImplementation(() => new Promise(r => { resolve = r }))
  render(<ArenaView />)
  fireEvent.click(screen.getByText('Train teams'))
  fireEvent.click(screen.getByText('Stop after match'))
  resolve(match as never)
  await waitFor(() => expect(screen.queryByText('Stop after match')).toBeNull())
  expect(api.arenaPlay).toHaveBeenCalledTimes(1)
})

it('reports a failed battle and stops the session', async () => {
  vi.mocked(api.arenaPlay).mockRejectedValue(new Error('Provider unavailable'))
  render(<ArenaView />)
  fireEvent.click(screen.getByText('Train teams'))
  await screen.findByText('Arena failed: Provider unavailable')
  expect(api.arenaPlay).toHaveBeenCalledTimes(1)
})
