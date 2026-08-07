import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../i18n/LanguageContext'
import SearchBar, { marketForTicker, normalizeTicker } from './SearchBar'

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
      expect(normalizeTicker(input)).toBe('301189.SZ')
    }
  )

  it.each(['600519', 'SH600519', '600519.SS', '600519.SH'])('resolves %s to 600519.SS', (input) => {
    expect(normalizeTicker(input)).toBe('600519.SS')
  })

  // The exchange comes from the code, never from what the user wrote — a 6xxxxx
  // code is Shanghai and a 000/300/301 code is Shenzhen no matter which prefix
  // or suffix was typed, so a mismatched one is corrected rather than trusted.
  it('derives the exchange from the code, overriding a wrong prefix/suffix', () => {
    expect(normalizeTicker('SZ600519')).toBe('600519.SS')
    expect(normalizeTicker('301189.SH')).toBe('301189.SZ')
  })

  it('routes each A-share board to the right exchange', () => {
    expect(normalizeTicker('688111')).toBe('688111.SS') // STAR market
    expect(normalizeTicker('601318')).toBe('601318.SS') // SSE main board
    expect(normalizeTicker('000001')).toBe('000001.SZ') // SZSE main board
    expect(normalizeTicker('300750')).toBe('300750.SZ') // ChiNext
  })

  // Anything without a 6-digit A-share reading is left exactly as typed and
  // allowed to fail as the invalid ticker it is, rather than being rewritten
  // into a market this app doesn't serve.
  it('leaves non-A-share input untouched', () => {
    expect(normalizeTicker('0700.HK')).toBe('0700.HK')
    expect(normalizeTicker('12345')).toBe('12345')
    expect(normalizeTicker('1234567')).toBe('1234567')
    expect(normalizeTicker('SZ12345')).toBe('SZ12345')
    expect(normalizeTicker('AAPL')).toBe('AAPL')
  })

  // Normalization is deliberately not gated on the market switcher (see the
  // comment on CN_CODE): typing SZ301189 while the switcher sat on its "US"
  // default — the state every visitor starts in — used to skip normalization
  // and send the raw string upstream. A US symbol has nothing to lose here,
  // since US listings are alphabetic and no 6-digit numeric code has a US
  // reading.
  it('applies the A-share rewrite with no market argument to gate it', () => {
    expect(normalizeTicker.length).toBe(1) // takes the raw string and nothing else
    expect(normalizeTicker('301189')).toBe('301189.SZ')
    expect(normalizeTicker('SZ301189')).toBe('301189.SZ')
    expect(normalizeTicker('aapl')).toBe('AAPL')
  })

  // Exchange qualifiers pasted from other terminals. Neither form resolves
  // upstream — "GOOGL.US" reaches Twelve Data as an unknown symbol — so both
  // used to come back as a failed card for a perfectly valid stock.
  it.each(['GOOGL.US', 'GOOGL US', 'googl.us', 'GOOGL  US'])('resolves %s to GOOGL', (input) => {
    expect(normalizeTicker(input)).toBe('GOOGL')
  })

  it('leaves real symbols that merely contain US alone', () => {
    // The qualifier needs a separator and has to be at the end, so none of
    // these lose characters to it.
    expect(normalizeTicker('USB')).toBe('USB')
    expect(normalizeTicker('USO')).toBe('USO')
    expect(normalizeTicker('US')).toBe('US')
  })

  // A Chinese keyboard defaults to a full-width IME, so these are ordinary
  // typing rather than an edge case: before NFKC folding, "３０１１８９" matched
  // no pattern at all and went upstream as literal full-width digits.
  it('folds full-width input to its ASCII equivalent', () => {
    expect(normalizeTicker('３０１１８９')).toBe('301189.SZ')
    expect(normalizeTicker('ＳＺ３０１１８９')).toBe('301189.SZ')
    expect(normalizeTicker('ＡＡＰＬ')).toBe('AAPL')
  })

  it('trims full-width spaces around the symbol', () => {
    expect(normalizeTicker('　AAPL　')).toBe('AAPL')
    expect(normalizeTicker('　301189　')).toBe('301189.SZ')
  })

  it('accepts a space between the exchange prefix and an A-share code', () => {
    expect(normalizeTicker('SZ 301189')).toBe('301189.SZ')
    expect(normalizeTicker('SH 600519')).toBe('600519.SS')
  })
})

// App.addStock reads this to move the switcher, so a card opened from anywhere
// — search, watchlist, the header's quick-open, the empty state — leaves the
// bucket agreeing with the symbol on screen.
describe('marketForTicker', () => {
  it('reads the bucket off a normalized A-share symbol', () => {
    expect(marketForTicker('301189.SZ')).toBe('cn')
    expect(marketForTicker('600519.SS')).toBe('cn')
    expect(marketForTicker('600519.ss')).toBe('cn')
    expect(marketForTicker(' 000001.SZ ')).toBe('cn')
  })

  // null rather than 'us': the symbol names no market, so App leaves the
  // switcher where the user put it instead of dragging a deliberately-set
  // "China" bucket back. Note a bare '301189' is null too — normalizeTicker
  // runs first, and this only ever sees what came out of it.
  it('returns null when the symbol names no market', () => {
    expect(marketForTicker('AAPL')).toBeNull()
    expect(marketForTicker('0700.HK')).toBeNull()
    expect(marketForTicker('301189')).toBeNull()
    expect(marketForTicker('BRK.B')).toBeNull()
  })
})

describe('SearchBar', () => {
  beforeEach(() => {
    apiSearch.mockReset()
    apiSearch.mockResolvedValue([])
  })

  function renderBar(onAdd, market = 'cn') {
    render(
      <LanguageProvider>
        <SearchBar market={market} onAdd={onAdd} />
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

  // The regression this whole change exists for. "US" is where the switcher
  // sits on every first visit, so this — not the 'cn' case above — is the path
  // a new user actually takes, and it used to ship the raw string upstream and
  // fail the card with nothing on screen naming the switcher as the cause.
  it.each(['SZ301189', '301189', '301189.SZ', 'SZ 301189', '３０１１８９'])(
    'adds %s as 301189.SZ even while the switcher is left on US',
    async (typed) => {
      const onAdd = vi.fn()
      const input = renderBar(onAdd, 'us')
      await userEvent.type(input, `${typed}{Enter}`)
      expect(onAdd).toHaveBeenCalledWith('301189.SZ')
    }
  )

  // Symmetry check: a US symbol typed while the switcher is on China still
  // resolves to itself, so the un-gating cuts one way only.
  it('leaves a US symbol alone while the switcher is on China', async () => {
    const onAdd = vi.fn()
    const input = renderBar(onAdd, 'cn')
    await userEvent.type(input, 'AAPL{Enter}')
    expect(onAdd).toHaveBeenCalledWith('AAPL')
  })
})
