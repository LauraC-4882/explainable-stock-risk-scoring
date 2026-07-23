import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { LanguageProvider, normaliseLang, useLanguage } from './LanguageContext'

// These exercise the real shipped locales rather than stand-ins. i18next is
// initialised once at module load with the real resources, so mocking the
// resource modules no longer buys anything — and the contract worth protecting
// is that `t()` still behaves exactly as it did before the engine swap.

function Probe({ path, vars }) {
  const { lang, setLang, t } = useLanguage()
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="out">{t(path, vars)}</span>
      <button onClick={() => setLang('zh-CN')}>zh-CN</button>
      <button onClick={() => setLang('zh-TW')}>zh-TW</button>
      <button onClick={() => setLang('zh')}>legacy-zh</button>
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

describe('normaliseLang', () => {
  it('accepts registered locales and maps legacy codes', () => {
    expect(normaliseLang('en')).toBe('en')
    expect(normaliseLang('zh-CN')).toBe('zh-CN')
    expect(normaliseLang('zh-TW')).toBe('zh-TW')
    // Pre-split preference must land on Simplified, not reset to English.
    expect(normaliseLang('zh')).toBe('zh-CN')
    expect(normaliseLang('zh-Hant')).toBe('zh-TW')
  })

  it('rejects unknown codes', () => {
    expect(normaliseLang('kl')).toBeNull()
    expect(normaliseLang(undefined)).toBeNull()
  })
})

describe('useLanguage / t()', () => {
  it('resolves a dotted path to its string', () => {
    renderProbe({ path: 'learn.notProbTitle' })
    expect(screen.getByTestId('out')).toHaveTextContent('It is not a probability')
  })

  it('interpolates {name}-style placeholders', () => {
    renderProbe({ path: 'coldStart.elapsed', vars: { seconds: 42 } })
    expect(screen.getByTestId('out')).toHaveTextContent('42s elapsed')
  })

  it('renders the path for a key that does not exist', () => {
    renderProbe({ path: 'nope.not.here' })
    expect(screen.getByTestId('out')).toHaveTextContent('nope.not.here')
  })

  it('switches to Simplified and then Traditional', async () => {
    const user = userEvent.setup()
    renderProbe({ path: 'learn.title' })
    expect(screen.getByTestId('lang')).toHaveTextContent('en')

    await user.click(screen.getByText('zh-CN'))
    expect(screen.getByTestId('lang')).toHaveTextContent('zh-CN')
    expect(screen.getByTestId('out')).toHaveTextContent('风险')

    await user.click(screen.getByText('zh-TW'))
    expect(screen.getByTestId('lang')).toHaveTextContent('zh-TW')
    expect(screen.getByTestId('out')).toHaveTextContent('風險')
  })

  it('maps a legacy zh preference onto Simplified', async () => {
    const user = userEvent.setup()
    renderProbe({ path: 'learn.title' })
    await user.click(screen.getByText('legacy-zh'))
    expect(screen.getByTestId('lang')).toHaveTextContent('zh-CN')
  })

  it('ignores an unknown language code', async () => {
    const user = userEvent.setup()
    renderProbe({ path: 'learn.title' })
    await user.click(screen.getByText('bogus'))
    expect(screen.getByTestId('lang')).toHaveTextContent('en')
  })

  it('persists the choice across remounts', async () => {
    const user = userEvent.setup()
    const { unmount } = renderProbe({ path: 'learn.title' })
    await user.click(screen.getByText('zh-TW'))
    unmount()

    renderProbe({ path: 'learn.title' })
    expect(screen.getByTestId('lang')).toHaveTextContent('zh-TW')
  })
})
