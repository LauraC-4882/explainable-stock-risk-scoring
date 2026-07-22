import { render } from '@testing-library/react'
import { LanguageProvider } from '../i18n/LanguageContext'

// Most components call useLanguage(), and several also call useAuth(); both
// throw outside their provider. Rendering through the real providers (rather
// than stubbing the hooks) means the tests also exercise the actual English
// strings users see, so a deleted locale key fails a component test.
export function renderWithProviders(ui, { wrapper: Extra } = {}) {
  const inner = Extra ? <Extra>{ui}</Extra> : ui
  return render(<LanguageProvider>{inner}</LanguageProvider>)
}

// jsdom normalises inline colours to rgb(); comparisons against the hex
// constants the components use need the same normalisation.
export function hexToRgb(hex) {
  const [, r, g, b] = /^#(\w{2})(\w{2})(\w{2})$/.exec(hex)
  return `rgb(${parseInt(r, 16)}, ${parseInt(g, 16)}, ${parseInt(b, 16)})`
}
