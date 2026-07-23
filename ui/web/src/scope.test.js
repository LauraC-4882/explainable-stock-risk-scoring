import { describe, expect, it } from 'vitest'

// Hong Kong was dropped from the supported market scope (2026-07-22): the
// universe is US equities + mainland China A-shares only. That decision lives
// in prose (README, module docstrings) — and prose doesn't fail CI. The last
// regression proved it: the English strings were cleaned up, the Chinese ones
// weren't, and 港股/香港 shipped to production because nothing checked. This
// file is the check.
//
// Two tiers, because comments legitimately *explain* the exclusion in English
// ("Hong Kong listings are out of scope" — see MarketSwitcher.jsx, utils.js):
//  - source files: only tokens with no legitimate use anywhere — Chinese
//    HK market terms and the HK ticker/index notation itself.
//  - locale files: every value is user-facing, so the English name is banned
//    there too.
const SOURCE_FORBIDDEN = [/港股/, /香港/, /恒生/, /恆生/, /\.HK\b/i, /\bHSI\b/i]
const LOCALE_FORBIDDEN = [...SOURCE_FORBIDDEN, /hong\s*kong/i]

// Raw text of every source and locale file. Test files are excluded so the
// patterns above don't match themselves.
const sourceFiles = import.meta.glob(['./**/*.{js,jsx}', '!./**/*.test.*'], {
  query: '?raw',
  import: 'default',
  eager: true,
})
const localeFiles = import.meta.glob('./i18n/locales/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
})

function violations(files, patterns) {
  return Object.entries(files).flatMap(([path, text]) =>
    text
      .split('\n')
      .flatMap((line, i) =>
        patterns
          .filter((p) => p.test(line))
          .map((p) => `${path}:${i + 1} matches ${p} → ${line.trim().slice(0, 100)}`)
      )
  )
}

describe('market scope guard (US + CN only, no Hong Kong)', () => {
  it('found the files it claims to guard', () => {
    // An empty glob would make the guards below pass vacuously.
    expect(Object.keys(sourceFiles).length).toBeGreaterThan(20)
    expect(Object.keys(localeFiles).length).toBe(3)
  })

  it('has no Hong Kong market tokens anywhere in UI source', () => {
    expect(violations(sourceFiles, SOURCE_FORBIDDEN)).toEqual([])
  })

  it('has no Hong Kong references in any locale, any language', () => {
    // This is the tier the en-fixed-zh-missed regression slipped through.
    expect(violations(localeFiles, LOCALE_FORBIDDEN)).toEqual([])
  })
})
