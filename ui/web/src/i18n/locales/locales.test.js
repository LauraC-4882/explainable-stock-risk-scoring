import { describe, expect, it } from 'vitest'
import en from './en'
import zh from './zh'

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

const enPaths = leafPaths(en)
const zhPaths = leafPaths(zh)

describe('locale parity', () => {
  it('has the same key tree in en and zh', () => {
    // A key added to one locale only degrades silently in the other (English
    // leaks into a Chinese screen), so it has to fail here instead.
    const zhSet = new Set(zhPaths)
    const enSet = new Set(enPaths)
    expect(enPaths.filter((p) => !zhSet.has(p))).toEqual([])
    expect(zhPaths.filter((p) => !enSet.has(p))).toEqual([])
  })

  it('has no empty strings', () => {
    const lookup = (dict, path) => path.split('.').reduce((acc, k) => acc?.[k], dict)
    const blank = (dict) =>
      enPaths.filter((p) => typeof lookup(dict, p) === 'string' && lookup(dict, p).trim() === '')
    expect(blank(en)).toEqual([])
    expect(blank(zh)).toEqual([])
  })

  it('keeps the same placeholders in both locales', () => {
    // A translation that drops {ticker} renders a sentence with a hole in it;
    // one that invents {stock} renders literal braces to the user.
    const lookup = (dict, path) => path.split('.').reduce((acc, k) => acc?.[k], dict)
    const mismatches = enPaths.filter((p) => {
      const e = lookup(en, p)
      const z = lookup(zh, p)
      if (typeof e !== 'string' || typeof z !== 'string') return false
      return JSON.stringify(placeholders(e)) !== JSON.stringify(placeholders(z))
    })
    expect(mismatches).toEqual([])
  })
})
