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
