import { screen } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import ColdStartBanner from './ColdStartBanner'

// The banner exists for one measured condition: Render's free instance takes
// ~100s to boot from sleep, versus ~1s warm. The two cases that matter are
// "warm — never show it" (a spurious banner would itself look broken) and
// "cold — show it and keep counting".
vi.mock('../api', () => ({ apiHealth: vi.fn() }))
const { apiHealth } = await import('../api')

describe('ColdStartBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('stays hidden on a warm instance that answers within the grace period', async () => {
    apiHealth.mockResolvedValue(true)
    renderWithProviders(<ColdStartBanner />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('appears once a cold boot exceeds the grace period, and counts elapsed time', async () => {
    // A boot that hasn't answered yet — the promise simply never settles.
    apiHealth.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<ColdStartBanner />)

    // Before the grace period nothing is shown.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    const banner = screen.getByRole('status')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveTextContent(/waking the free instance/i)
    // Sets expectations about duration rather than leaving a bare spinner.
    expect(banner).toHaveTextContent(/60/)
    expect(banner).toHaveTextContent(/6s elapsed/)
  })

  it('disappears when the instance finishes booting', async () => {
    let resolveHealth
    apiHealth.mockReturnValue(
      new Promise((resolve) => {
        resolveHealth = resolve
      })
    )
    renderWithProviders(<ColdStartBanner />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.getByRole('status')).toBeInTheDocument()

    await act(async () => {
      resolveHealth(true)
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('still resolves the banner if the probe fails, rather than hanging forever', async () => {
    apiHealth.mockRejectedValue(new Error('network down'))
    renderWithProviders(<ColdStartBanner />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
