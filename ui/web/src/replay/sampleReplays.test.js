import { describe, expect, it } from 'vitest'
import en from '../i18n/locales/en.json'
import { SAMPLE_REPLAYS } from './sampleReplays'

// The bundle is generated (scripts/generate_sample_replays.py); these tests
// pin the contract the viewer depends on, so a regeneration that drifts —
// or a new harness event type without a label — fails here instead of
// rendering raw event keys to users.

const CORE_SURFACES = ['score', 'portfolio', 'community', 'crash', 'comprehension']

describe('bundled sample replays', () => {
  it('ships one journey per core surface, in order', () => {
    expect(SAMPLE_REPLAYS.map((s) => s.id)).toEqual(CORE_SURFACES)
  })

  it('every sample is a well-formed replay with steps and a summary', () => {
    for (const { id, replay } of SAMPLE_REPLAYS) {
      expect(Array.isArray(replay.steps), id).toBe(true)
      expect(replay.steps.length, id).toBeGreaterThan(1)
      expect(replay.summary, id).toBeTruthy()
      expect(replay.archetype, id).toBeTruthy()
      expect(replay.simulation_seed, id).not.toBeUndefined()
    }
  })

  it('every event in every sample has a localized step label and a picker label', () => {
    for (const { id, replay } of SAMPLE_REPLAYS) {
      expect(en.replay.samples[id], `picker label for ${id}`).toBeTruthy()
      for (const step of replay.steps) {
        expect(en.replay.stepLabels[step.event], `stepLabels.${step.event} (in ${id})`).toBeTruthy()
      }
    }
  })

  it('each journey actually exhibits its surface signature events', () => {
    const events = Object.fromEntries(
      SAMPLE_REPLAYS.map(({ id, replay }) => [id, replay.steps.map((s) => s.event)])
    )
    expect(events.score).toContain('score_viewed')
    expect(events.portfolio).toContain('risk_contribution_viewed')
    expect(events.community).toContain('community_post_reported')
    expect(events.crash).toContain('user_action_intent_recorded')
    expect(events.comprehension).toContain('comprehension_answered')
  })
})
