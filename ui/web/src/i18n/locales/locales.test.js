import { describe, expect, it } from 'vitest'
import en from './en.json'
import zhCN from './zh-CN.json'
import zhTW from './zh-TW.json'

// Flattened leaf paths — the unit a translator actually adds or forgets.
function leafPaths(node, prefix = '') {
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return value && typeof value === 'object' && !Array.isArray(value)
      ? leafPaths(value, path)
      : [path]
  })
}

// Placeholders the UI fills at render time ({ticker}, {sessions}…).
const placeholders = (s) => (s.match(/\{(\w+)\}/g) || []).sort()
const lookup = (dict, path) => path.split('.').reduce((acc, k) => acc?.[k], dict)

const TRANSLATIONS = { 'zh-CN': zhCN, 'zh-TW': zhTW }
const enPaths = leafPaths(en)

describe('locale parity', () => {
  it.each(Object.keys(TRANSLATIONS))('has the same key tree in en and %s', (code) => {
    // A key added to one locale only degrades silently in the other (English
    // leaks into a Chinese screen), so it has to fail here instead.
    const paths = leafPaths(TRANSLATIONS[code])
    const set = new Set(paths)
    const enSet = new Set(enPaths)
    expect(enPaths.filter((p) => !set.has(p))).toEqual([])
    expect(paths.filter((p) => !enSet.has(p))).toEqual([])
  })

  it.each(['en', ...Object.keys(TRANSLATIONS)])('has no empty strings in %s', (code) => {
    const dict = code === 'en' ? en : TRANSLATIONS[code]
    const blank = enPaths.filter(
      (p) => typeof lookup(dict, p) === 'string' && lookup(dict, p).trim() === ''
    )
    expect(blank).toEqual([])
  })

  it.each(Object.keys(TRANSLATIONS))('keeps the same placeholders in %s', (code) => {
    // A translation that drops {ticker} renders a sentence with a hole in it;
    // one that invents {stock} renders literal braces to the user.
    const dict = TRANSLATIONS[code]
    const mismatches = enPaths.filter((p) => {
      const e = lookup(en, p)
      const z = lookup(dict, p)
      if (typeof e !== 'string' || typeof z !== 'string') return false
      return JSON.stringify(placeholders(e)) !== JSON.stringify(placeholders(z))
    })
    expect(mismatches).toEqual([])
  })

  it('actually converted zh-TW to traditional characters', () => {
    // zh-TW is generated from zh-CN (OpenCC s2tw). If generation silently
    // no-ops, the Traditional option would ship Simplified text — visibly wrong
    // to the users who selected it, and invisible to every other check here.
    const differing = enPaths.filter((p) => {
      const cn = lookup(zhCN, p)
      const tw = lookup(zhTW, p)
      return typeof cn === 'string' && typeof tw === 'string' && cn !== tw
    })
    expect(differing.length).toBeGreaterThan(50)
    expect(lookup(zhTW, 'learn.title')).toContain('風險')
  })
})

// ── Residual-English gate ────────────────────────────────────────────────────
//
// The parity checks above cannot see the one remaining failure mode: a zh leaf
// that is still the untranslated English original. It has the same key, is
// non-empty, carries identical placeholders, and (being copied into both zh
// files before OpenCC ran) can even survive the zh-TW≠zh-CN check. So: a leaf
// that is byte-identical to its en counterpart AND contains no CJK character
// is flagged, unless its path is in the explicit language-neutral allowlist.

const CJK = /[一-鿿㐀-䶿]/

// Every entry deliberately identical across locales, audited 2026-08-29:
// brand, metric acronyms, tech-stack names, numeric stat values. Two are
// borderline and left for a product call, not silently translated by a test
// PR: emptyState.slogan (an English slogan shown on zh screens) and
// governance.minAuc ("Walk-forward ROC AUC" is translatable prose).
const LANGUAGE_NEUTRAL_LEAVES = new Set([
  'header.title',
  'emptyState.slogan',
  'metrics.var95',
  'metrics.rsi',
  'about.stats.stocks.value',
  'about.stats.auc.value',
  'about.stats.weight.value',
  'tech.metrics.auc.value',
  'tech.metrics.tests.value',
  'tech.stack.react.name',
  'tech.stack.tailwind.name',
  'tech.stack.recharts.name',
  'tech.stack.framer.name',
  'tech.stack.i18next.name',
  'tech.stack.fastapi.name',
  'tech.stack.sqlmodel.name',
  'tech.stack.xgboost.name',
  'tech.stack.shap.name',
  'tech.stack.data.name',
  'tech.stack.render.name',
  'governance.sha',
  'governance.minAuc',
])

function residualEnglishLeaves(enDict, zhDict, paths, allowlist) {
  return paths.filter((p) => {
    const e = lookup(enDict, p)
    const z = lookup(zhDict, p)
    if (typeof e !== 'string' || typeof z !== 'string') return false
    if (allowlist.has(p)) return false
    return z === e && !CJK.test(z)
  })
}

const cjkShare = (dict, paths) => {
  const strings = paths.filter((p) => typeof lookup(dict, p) === 'string')
  return strings.filter((p) => CJK.test(lookup(dict, p))).length / strings.length
}

describe('residual English in zh locales', () => {
  // Key-set parity for all three files is asserted by 'locale parity' above;
  // this block leans on it rather than restating the same expectation.

  it.each(Object.keys(TRANSLATIONS))('%s has no untranslated English leaves', (code) => {
    const leftovers = residualEnglishLeaves(
      en,
      TRANSLATIONS[code],
      enPaths,
      LANGUAGE_NEUTRAL_LEAVES
    )
    expect(leftovers).toEqual([])
  })

  it.each(Object.keys(TRANSLATIONS))('%s stays overwhelmingly CJK', (code) => {
    // Measured 0.967 for both zh files when this gate landed; 0.9 leaves room
    // for more language-neutral labels without tolerating a mass regression
    // (e.g. a bad merge restoring English copy that is not byte-identical,
    // which the leaf check above cannot see).
    expect(cjkShare(TRANSLATIONS[code], enPaths)).toBeGreaterThan(0.9)
  })

  it('the residual-English detector can actually fire', () => {
    // Fire-check, same rationale as tests/test_docs_consistency.py's: a gate
    // that never trips proves nothing. Synthetic dicts exercise flag,
    // CJK-clean, and allowlist paths without touching the real locales.
    const fakeEn = { a: 'Sign in', b: 'Portfolio', c: 'VaR 95%' }
    const fakeZh = { a: 'Sign in', b: '投资组合', c: 'VaR 95%' }
    const flagged = residualEnglishLeaves(fakeEn, fakeZh, ['a', 'b', 'c'], new Set(['c']))
    expect(flagged).toEqual(['a'])
    expect(cjkShare(fakeZh, ['a', 'b', 'c'])).toBeCloseTo(1 / 3)
  })
})
