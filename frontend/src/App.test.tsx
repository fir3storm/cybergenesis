import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })))

describe('App', () => {
  it('renders CYBERGENESIS welcome honestly when backend is down', async () => {
    render(<App />)
    expect(await screen.findByText('The Autonomous Self-Defending Digital Twin')).toBeTruthy()
    expect(screen.getAllByText(/Created by Dr\. Abhirup Guha/).length).toBeGreaterThan(0)
    expect(screen.getByText(/OFFLINE SIMULATION/)).toBeTruthy()
  })
})
