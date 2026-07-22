import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LanguageProvider, useLanguage } from './LanguageContext'

// Stand-in locales instead of the shipped ones: the fallback path only exists
// for keys a translator hasn't reached yet, and locales.test.js asserts the
// real files have no such gap. Mocking keeps this file testing t()'s logic
// rather than today's translation coverage.
vi.mock('./locales/en', () => ({
  default: {
    card: { title: 'Risk score', greeting: 'Hello {name}, {ticker} is risky' },
    onlyEnglish: 'Untranslated {name}',
  },
}))
vi.mock('./locales/zh', () => ({
  default: { card: { title: '风险评分', greeting: '你好 {name}，{ticker} 有风险' } },
}))

function Probe({ path, vars }) {
  const { lang, setLang, t } = useLanguage()
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="out">{t(path, vars)}</span>
      <button onClick={() => setLang('zh')}>zh</button>
      <button onClick={() => setLang('kl')}>bogus</button>
    </div>
  )
}

const renderProbe = (props) =>
  render(
    <LanguageProvider>
      <Probe {...props} />
    </LanguageProvider>
  )

describe('useLanguage / t()', () => {
  it('resolves a dotted path to its string', () => {
    renderProbe({ path: 'card.title' })
    expect(screen.getByTestId('out')).toHaveTextContent('Risk score')
  })

  it('interpolates {vars}', () => {
    renderProbe({ path: 'card.greeting', vars: { name: 'Ada', ticker: 'TSLA' } })
    expect(screen.getByTestId('out')).toHaveTextContent('Hello Ada, TSLA is risky')
  })

  it('leaves a placeholder alone when no value is supplied', () => {
    renderProbe({ path: 'card.greeting', vars: { name: 'Ada' } })
    expect(screen.getByTestId('out')).toHaveTextContent('Hello Ada, {ticker} is risky')
  })

  it('falls back to English rather than rendering the raw path', async () => {
    renderProbe({ path: 'onlyEnglish' })
    await userEvent.click(screen.getByText('zh'))
    // Untranslated in zh: the user reads English, never "onlyEnglish".
    expect(screen.getByTestId('lang')).toHaveTextContent('zh')
    expect(screen.getByTestId('out')).toHaveTextContent('Untranslated {name}')
    expect(screen.getByTestId('out')).not.toHaveTextContent('onlyEnglish')
  })

  it('returns the path only when the key exists in no locale at all', () => {
    // Last resort, and a deliberate dev-facing signal: a path on screen means
    // the key was never written, which is a different bug from a missing
    // translation and shouldn't be disguised as blank space.
    renderProbe({ path: 'card.missingEntirely' })
    expect(screen.getByTestId('out')).toHaveTextContent('card.missingEntirely')
  })

  it('interpolates a key that exists only in English', async () => {
    renderProbe({ path: 'onlyEnglish', vars: { name: 'Ada' } })
    await userEvent.click(screen.getByText('zh'))
    // Regression guard: substitution must happen AFTER the English fallback,
    // otherwise an untranslated key renders literal "{name}" braces.
    expect(screen.getByTestId('out')).toHaveTextContent('Untranslated Ada')
  })

  it('switches locale and persists the choice', async () => {
    renderProbe({ path: 'card.title' })
    await userEvent.click(screen.getByText('zh'))
    expect(screen.getByTestId('out')).toHaveTextContent('风险评分')
    expect(localStorage.getItem('stock-risk-lang')).toBe('zh')
  })

  it('ignores an unsupported locale instead of blanking the UI', async () => {
    renderProbe({ path: 'card.title' })
    await userEvent.click(screen.getByText('bogus'))
    expect(screen.getByTestId('lang')).toHaveTextContent('en')
    expect(screen.getByTestId('out')).toHaveTextContent('Risk score')
  })

  it('throws outside a provider rather than silently rendering nothing', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Probe path="card.title" />)).toThrow(/LanguageProvider/)
    quiet.mockRestore()
  })
})
