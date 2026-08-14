import { screen, waitFor, within } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../auth/AuthContext'
import { renderWithProviders } from '../test/utils'
import GovernancePanel, { barWidth, statusTone } from './GovernancePanel'

// The response shape /api/governance/model actually returns — the two halves
// (recorded vs. deployed) kept apart, exactly as the endpoint sends them.
const snapshot = (over = {}) => ({
  model_name: 'downside_risk',
  registry_present: false,
  registry_path: 'models/registry.json',
  champion: null,
  challengers: [],
  previous_champion: null,
  versions: [],
  artefact: {
    path: 'models/artefacts/downside_risk_xgb.joblib',
    exists: true,
    loaded: true,
    size_bytes: 509294,
    sha256: 'e72045907caa0d1a7af60a8158ef250060000fab2455b997cca8a0ec205bab19',
    provenance: {
      commit: 'c435488ce15fa18420259adb6babab2e255cf4f0',
      committed_at: '2026-07-18T16:50:40-07:00',
      subject: 'Add ENABLE_ML memory toggle',
    },
    hyperparameters: { n_estimators: 300, max_depth: 5 },
    calibrated: true,
    feature_schema_version: '1.0.0',
    feature_count: 19,
    top_features: [
      { feature: 'volatility__vol_63d', importance: 0.130935 },
      { feature: 'volatility__vol_21d', importance: 0.085977 },
    ],
  },
  artefact_matches_record: null,
  lifecycle: {
    states: [
      { state: 'development', to: ['retired', 'validated'] },
      { state: 'validated', to: ['approved', 'development', 'retired'] },
      { state: 'approved', to: ['active', 'retired', 'shadow'] },
      { state: 'shadow', to: ['active', 'approved', 'retired'] },
      { state: 'active', to: ['degraded', 'retired'] },
      { state: 'degraded', to: ['retired', 'validated'] },
      { state: 'retired', to: [] },
    ],
    terminal: ['retired'],
  },
  default_thresholds: {
    min_roc_auc: 0.6,
    max_brier: 0.25,
    max_drift_psi: 0.2,
    require_calibration_improves_brier: true,
  },
  statuses: [],
  ...over,
})

function AutoOpen({ children }) {
  const { openGovernancePanel } = useAuth()
  useEffect(() => {
    openGovernancePanel()
  }, [openGovernancePanel])
  return children
}

function renderOpen() {
  return renderWithProviders(
    <AuthProvider>
      <AutoOpen>
        <GovernancePanel />
      </AutoOpen>
    </AuthProvider>
  )
}

function mockGovernance(body) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url) =>
      String(url).includes('/api/governance/model')
        ? Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
        : Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    )
  )
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('GovernancePanel', () => {
  it('renders the missing-registry case as a stated finding, not blank space', async () => {
    // The regression this guards: an empty governance page reads as "nothing
    // wrong here". The unrecorded state has to be legible as unrecorded, and
    // must name the file whose absence causes it.
    mockGovernance(snapshot())
    renderOpen()

    expect(await screen.findByText(/No governance record/i)).toBeInTheDocument()
    expect(screen.getByText(/models\/registry\.json/)).toBeInTheDocument()
    // ...and it stays actionable: the command that writes a real record.
    expect(screen.getByText(/scripts\/train\.py/)).toBeInTheDocument()
  })

  it('never invents a metric to fill the gap', async () => {
    mockGovernance(snapshot())
    renderOpen()
    await screen.findByText(/No governance record/i)

    // 0.671 is the repo's published walk-forward AUC. With no registry record
    // it must NOT appear as this model's measured metric — substituting a
    // README number for a governance record is the exact dishonesty the
    // absent-state design exists to prevent. (0.6 is the threshold, a
    // different claim, and is expected to render.)
    expect(screen.queryByText(/0\.671/)).not.toBeInTheDocument()
    expect(screen.getByText(/≥ 0\.6/)).toBeInTheDocument()
  })

  it('shows the champion and its full lifecycle route when a record exists', async () => {
    mockGovernance(
      snapshot({
        registry_present: true,
        artefact_matches_record: true,
        champion: {
          name: 'downside_risk',
          version: '1.0.0',
          status: 'active',
          metrics: { roc_auc: 0.671 },
          thresholds_pass: true,
          threshold_failures: [],
          dataset_hash: 'abc123def456abc123def456',
          history: [],
        },
      })
    )
    renderOpen()

    expect(await screen.findByText('downside_risk v1.0.0')).toBeInTheDocument()
    expect(screen.getByText('0.6710')).toBeInTheDocument()
    expect(screen.queryByText(/No governance record/i)).not.toBeInTheDocument()
  })

  it('flags a record that points at a different artefact than the one served', async () => {
    mockGovernance(
      snapshot({
        registry_present: true,
        artefact_matches_record: false,
        champion: {
          name: 'downside_risk',
          version: '1.0.0',
          status: 'active',
          metrics: {},
          thresholds_pass: true,
          threshold_failures: [],
          history: [],
        },
      })
    )
    renderOpen()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/not answering requests/i)
  })

  it('renders the deployed artefact, including that it is loaded', async () => {
    mockGovernance(snapshot())
    renderOpen()

    expect(await screen.findByText(/downside_risk_xgb\.joblib/)).toBeInTheDocument()
    expect(screen.getByText(/c435488ce1/)).toBeInTheDocument()
    expect(screen.getByText(/Loaded and answering requests/i)).toBeInTheDocument()
    // Top 2 of 19 — the count is the full schema, not the truncated list.
    expect(screen.getByText(/Top 2 of 19/i)).toBeInTheDocument()
    expect(screen.getByText('volatility__vol_63d')).toBeInTheDocument()
  })

  it('says the artefact is not being served when ML is off', async () => {
    mockGovernance(
      snapshot({
        artefact: {
          ...snapshot().artefact,
          loaded: false,
          feature_count: null,
          top_features: [],
        },
      })
    )
    renderOpen()

    expect(await screen.findByText(/ENABLE_ML=0/)).toBeInTheDocument()
  })

  it('renders the two absent lifecycle edges that are the actual control', async () => {
    mockGovernance(snapshot())
    renderOpen()
    await screen.findByText(/Enforced lifecycle/i)

    // Per-chip, not on the row's concatenated textContent: the chips render
    // without separators, so "activeretiredshadow" defeats a /\bactive\b/ on
    // the joined string and the assertion would pass for the wrong reason.
    const chips = (state) =>
      within(screen.getByTestId(`lifecycle-${state}`))
        .getAllByText(/.+/)
        .map((el) => el.textContent)

    // development's row must not offer `active`, and degraded's must not
    // either — these are the edges the registry raises on.
    expect(chips('development')).not.toContain('active')
    expect(chips('degraded')).not.toContain('active')
    // The rows that DO reach active still say so, so the assertions above are
    // testing the graph rather than a rendering that dropped the chips.
    expect(chips('approved')).toContain('active')
    expect(chips('shadow')).toContain('active')
  })

  it('waits for data rather than rendering a half-populated page', async () => {
    mockGovernance(snapshot())
    renderOpen()
    // Nothing from the payload before the fetch resolves.
    expect(screen.queryByText(/downside_risk_xgb\.joblib/)).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/downside_risk_xgb\.joblib/)).toBeInTheDocument())
  })

  it('reports an unreadable governance state instead of an empty page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    )
    renderOpen()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be read/i)
  })
})

describe('barWidth', () => {
  it('scales against the top feature so the ranking stays readable', () => {
    // Gain importances sum to 1 across ~19 features, so the leader is ~0.13.
    // On an absolute 0-1 scale every bar would be a 13%-or-less sliver and the
    // ranking — the entire point of the chart — would be invisible.
    expect(barWidth(0.13, 0.13)).toBe(100)
    expect(barWidth(0.065, 0.13)).toBe(50)
  })

  it('keeps a hairline for near-zero importances instead of nothing', () => {
    expect(barWidth(0.0001, 0.13)).toBe(2)
  })

  it('does not divide by zero when there are no features', () => {
    expect(barWidth(0.1, 0)).toBe(0)
    expect(barWidth(undefined, 0.13)).toBe(0)
  })
})

describe('statusTone', () => {
  it('gives active and degraded opposing tones, and never colour alone', () => {
    expect(statusTone('active')).not.toBe(statusTone('degraded'))
    // Every status still gets a class, so an unknown one from a future
    // ModelStatus renders styled rather than invisible.
    expect(statusTone('some_future_state')).toBeTruthy()
  })
})
