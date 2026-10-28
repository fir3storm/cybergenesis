import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { JUDGE_STEPS, JudgeCaptions, judgeStepIndex } from './judgeMode'
import { BriefingCard } from './briefing'
import { api } from '../services/api'

vi.mock('../services/api', () => ({ api: { briefing: vi.fn(), briefingMarkdown: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

const offline = {
  facts: { run_id: 'r1', outcome: 'FAIL' },
  narrative: { headline: 'Simulated Ransomware NOT stopped', summary: 'Risk unchanged.', board_asks: ['Approve a follow-up exercise'], mode: 'offline', model: 'deterministic' },
  compliance: [{ framework: 'NIST CSF 2.0', id: 'ID.IM-02', title: 'Improvements', evidenced_by: ['verification replay'] }],
  disclaimer: 'not an audit opinion',
}

it('maps every run state to a judge step and shows FAIL honestly', () => {
  expect(judgeStepIndex('VERIFYING')).toBe(JUDGE_STEPS.findIndex((s) => s.title === 'Verify'))
  expect(judgeStepIndex('unknown')).toBe(0)
  render(<JudgeCaptions state="COMPLETED" outcome="FAIL" onClose={() => {}} />)
  expect(screen.getByText(/FAIL: the defense did not close the path/)).toBeTruthy()
})

it('briefing card labels deterministic text and surfaces an AI fallback reason', async () => {
  vi.mocked(api.briefing).mockResolvedValueOnce(offline as never)
    .mockResolvedValueOnce({ ...offline, narrative: { ...offline.narrative, fallback_reason: 'AI provider not configured' } } as never)
  render(<BriefingCard runId="r1" outcome="FAIL" />)
  await waitFor(() => expect(screen.getByText('Simulated Ransomware NOT stopped')).toBeTruthy())
  expect(screen.getByText('DETERMINISTIC')).toBeTruthy()
  expect(screen.getByText('CSF ID.IM-02')).toBeTruthy()
  fireEvent.click(screen.getByText('Draft with AI'))
  await waitFor(() => expect(screen.getByText(/AI provider not configured/)).toBeTruthy())
  expect(vi.mocked(api.briefing)).toHaveBeenLastCalledWith('r1', true)
})
