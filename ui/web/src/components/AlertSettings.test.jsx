import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { renderWithProviders } from '../test/utils'
import AlertSettings, { SPIKE_DEFAULT, parseSetting } from './AlertSettings'

const item = (over = {}) => ({
  id: 1,
  ticker: 'AAPL',
  market: 'us',
  alert_threshold: null,
  alert_spike_points: null,
  alert_sent_at: null,
  ...over,
})

function mockApi({ patchStatus = 200 } = {}) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url, opts = {}) => {
      const u = String(url)
      if (u.includes('/alerts') && opts.method === 'PATCH') {
        calls.push(JSON.parse(opts.body))
        return Promise.resolve({
          ok: patchStatus === 200,
          status: patchStatus,
          json: () =>
            Promise.resolve(
              patchStatus === 200
                ? { ...item(), ...JSON.parse(opts.body) }
                : { detail: 'nope' }
            ),
        })
      }
      // AuthContext restores a session on mount; no token in localStorage
      // means it never fires, but be safe.
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
  )
  return calls
}

function renderSettings(props) {
  return renderWithProviders(
    <AuthProvider>
      <AlertSettings {...props} />
    </AuthProvider>
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('parseSetting', () => {
  it('treats empty as unset, not as zero', () => {
    // The distinction the nullable columns exist for: 0 is the most sensitive
    // threshold a user can pick, so "" collapsing to 0 would silently arm an
    // alert on a control the user just cleared.
    expect(parseSetting('', { min: 0, max: 100 })).toBeNull()
    expect(parseSetting('0', { min: 0, max: 100 })).toBe(0)
  })

  it('clamps to the range the backend accepts', () => {
    expect(parseSetting('150', { min: 0, max: 100 })).toBe(100)
    expect(parseSetting('-5', { min: 0, max: 100 })).toBe(0)
    expect(parseSetting('0', { min: 1, max: 100 })).toBe(1)
  })

  it('rounds, because the score is displayed as an integer', () => {
    expect(parseSetting('70.6', { min: 0, max: 100 })).toBe(71)
  })

  it('rejects junk rather than sending NaN', () => {
    expect(parseSetting('abc', { min: 0, max: 100 })).toBeNull()
  })
})

describe('AlertSettings', () => {
  it('starts with both triggers off for a stock that has none', () => {
    mockApi()
    renderSettings({ item: item() })
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes).toHaveLength(2)
    expect(boxes[0]).not.toBeChecked()
    expect(boxes[1]).not.toBeChecked()
    // No number inputs until a trigger is enabled.
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it('enabling the spike trigger offers the documented default', async () => {
    const calls = mockApi()
    renderSettings({ item: item() })
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].spike_points).toBe(SPIKE_DEFAULT)
  })

  it('sends null to turn a trigger off, not a zero', async () => {
    const calls = mockApi()
    renderSettings({ item: item({ alert_threshold: 70 }) })
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].threshold).toBeNull()
  })

  it('saves an edited threshold on blur', async () => {
    const calls = mockApi()
    renderSettings({ item: item({ alert_threshold: 70 }) })
    const field = screen.getByRole('spinbutton')
    fireEvent.change(field, { target: { value: '85' } })
    fireEvent.blur(field)
    await waitFor(() => expect(calls.at(-1).threshold).toBe(85))
  })

  it('saves on Enter without submitting anything twice', async () => {
    const calls = mockApi()
    renderSettings({ item: item({ alert_threshold: 70 }) })
    const field = screen.getByRole('spinbutton')
    // Focus first: Enter commits by calling blur(), and blur() on an element
    // that was never focused is a no-op in jsdom (and in a browser). Typing
    // into a field you have not focused is not a real scenario either.
    field.focus()
    fireEvent.change(field, { target: { value: '80' } })
    fireEvent.keyDown(field, { key: 'Enter' })
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].threshold).toBe(80)
  })

  it('reports a failed save instead of looking saved', async () => {
    mockApi({ patchStatus: 422 })
    renderSettings({ item: item({ alert_threshold: 70 }) })
    const field = screen.getByRole('spinbutton')
    fireEvent.change(field, { target: { value: '85' } })
    fireEvent.blur(field)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
  })

  it('says when the last email went out', () => {
    mockApi()
    renderSettings({ item: item({ alert_threshold: 70, alert_sent_at: '2026-08-09T12:00:00Z' }) })
    expect(screen.getByText(/Last emailed/i)).toBeInTheDocument()
  })

  it('says nothing has been sent yet once a trigger is armed', () => {
    mockApi()
    renderSettings({ item: item({ alert_threshold: 70 }) })
    expect(screen.getByText(/No email sent yet/i)).toBeInTheDocument()
  })

  it('stays quiet when no trigger is set', () => {
    mockApi()
    renderSettings({ item: item() })
    expect(screen.queryByText(/No email sent yet/i)).not.toBeInTheDocument()
  })

  it('warns when the account has unsubscribed', async () => {
    // The account-level opt-out beats every per-stock setting, so a user who
    // unsubscribed weeks ago on another device must not be able to arm a
    // threshold here and reasonably expect an email. Not screenshot-covered:
    // reaching this state needs an unsubscribe token, which is only mintable
    // server-side by design.
    mockApi()
    localStorage.setItem('stock-risk-token', 'fake-token')
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        const u = String(url)
        if (u.includes('/api/auth/me')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ id: 1, email: 'a@b.c', email_alerts_enabled: false }),
          })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
      })
    )
    renderSettings({ item: item({ alert_threshold: 70 }) })
    expect(await screen.findByText(/will not send/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /turn them back on/i })).toBeInTheDocument()
  })
})
