import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../i18n/LanguageContext'
import MarketSwitcher from './MarketSwitcher'

function renderSwitcher(market, onChange = vi.fn()) {
  render(
    <LanguageProvider>
      <MarketSwitcher market={market} onChange={onChange} />
    </LanguageProvider>
  )
  return {
    us: screen.getByRole('button', { name: /US/ }),
    cn: screen.getByRole('button', { name: /China/ }),
    onChange,
  }
}

describe('MarketSwitcher', () => {
  // Before aria-pressed, selection existed only as a CSS fill: assistive tech
  // saw two identical buttons and no way to tell which market was live.
  it('exposes the live market through aria-pressed', () => {
    const { us, cn } = renderSwitcher('us')
    expect(us).toHaveAttribute('aria-pressed', 'true')
    expect(cn).toHaveAttribute('aria-pressed', 'false')
  })

  it('moves aria-pressed with the market prop', () => {
    const { us, cn } = renderSwitcher('cn')
    expect(us).toHaveAttribute('aria-pressed', 'false')
    expect(cn).toHaveAttribute('aria-pressed', 'true')
  })

  it('reports the picked market to its parent', async () => {
    const { cn, onChange } = renderSwitcher('us')
    await userEvent.click(cn)
    expect(onChange).toHaveBeenCalledWith('cn')
  })
})
