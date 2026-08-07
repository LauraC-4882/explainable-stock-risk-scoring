import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../i18n/LanguageContext'
import SearchBar, { normalizeTicker } from './SearchBar'

vi.mock('../api', () => ({ apiSearch: vi.fn() }))
import { apiSearch } from '../api'

describe('normalizeTicker', () => {
  // Every shape a user actually types for the same Shenzhen ChiNext listing.
  // SZ301189 is what Eastmoney and Futu display, and before this normalization
  // it was passed to the backend verbatim, where _is_cn_ticker() (which tests
  // for a .SS/.SZ *suffix*) rejected it, routed it to yfinance, and the card
  // failed with "no price data available for 'SZ301189'".
  it.each(['301189', 'SZ301189', '301189.SZ', '301189.sz', ' sz301189 '])(
    'resolves %s to 301189.SZ',
    (input) => {
      expect(normalizeTicker(input, 'cn')).toBe('301189.SZ')
    }
  )

  it.each(['600519', 'SH600519', '600519.SS', '600519.SH'])('resolves %s to 600519.SS', (input) => {
    expect(normalizeTicker(input, 'cn')).toBe('600519.SS')
  })

  // The exchange comes from the code, never from what the user wrote — a 6xxxxx
  // code is Shanghai and a 000/300/301 code is Shenzhen no matter which prefix
  // or suffix was typed, so a mismatched one is corrected rather than trusted.
  it('derives the exchange from the code, overriding a wrong prefix/suffix', () => {
    expect(normalizeTicker('SZ600519', 'cn')).toBe('600519.SS')
    expect(normalizeTicker('301189.SH', 'cn')).toBe('301189.SZ')
  })

  it('routes each A-share board to the right exchange', () => {
    expect(normalizeTicker('688111', 'cn')).toBe('688111.SS') // STAR market
    expect(normalizeTicker('601318', 'cn')).toBe('601318.SS') // SSE main board
    expect(normalizeTicker('000001', 'cn')).toBe('000001.SZ') // SZSE main board
    expect(normalizeTicker('300750', 'cn')).toBe('300750.SZ') // ChiNext
  })

  // Anything without a 6-digit A-share reading is left exactly as typed and
  // allowed to fail as the invalid ticker it is, rather than being rewritten
  // into a market this app doesn't serve.
  it('leaves non-A-share input untouched', () => {
    expect(normalizeTicker('0700.HK', 'cn')).toBe('0700.HK')
    expect(normalizeTicker('12345', 'cn')).toBe('12345')
    expect(normalizeTicker('1234567', 'cn')).toBe('1234567')
    expect(normalizeTicker('SZ12345', 'cn')).toBe('SZ12345')
    expect(normalizeTicker('AAPL', 'cn')).toBe('AAPL')
  })

  it('never rewrites anything in the US bucket', () => {
    expect(normalizeTicker('301189', 'us')).toBe('301189')
    expect(normalizeTicker('SZ301189', 'us')).toBe('SZ301189')
    expect(normalizeTicker('aapl', 'us')).toBe('AAPL')
  })
})

describe('SearchBar', () => {
  beforeEach(() => {
    apiSearch.mockReset()
    apiSearch.mockResolvedValue([])
  })

  function renderBar(onAdd) {
    render(
      <LanguageProvider>
        <SearchBar market="cn" onAdd={onAdd} />
      </LanguageProvider>
    )
    return screen.getByRole('textbox')
  }

  // The whole point of the fix: both spellings must land on the same card.
  it.each(['SZ301189', '301189'])('adds %s as 301189.SZ on Enter', async (typed) => {
    const onAdd = vi.fn()
    const input = renderBar(onAdd)
    await userEvent.type(input, `${typed}{Enter}`)
    expect(onAdd).toHaveBeenCalledWith('301189.SZ')
  })
})
