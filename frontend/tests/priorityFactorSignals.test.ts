// The Prioritization Agent's factor-card colours: only the four saved signal
// values are coloured; anything else is grey "Not classified". Run: npm test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { factorSignalDisplay, NOT_CLASSIFIED } from '../src/utils/priorityFactorSignals.ts'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const UTIL = source('../src/utils/priorityFactorSignals.ts')
const CSS = source('../src/pages/AdminRaiseCapacityReview.css')
const PC_CSS = source('../src/pages/AdminProgramChangeReview.css')

const SIGNALS = {
  graduation: 'HIGHER',
  degree_progress: 'LOWER',
  course_requirement: 'REVIEW',
  course_availability: 'NEUTRAL',
  previous_attempts: 'HIGHER',
  prerequisite: 'LOWER',
  progression: 'NEUTRAL',
}

test('each of the four signals has its colour and label', () => {
  assert.deepEqual(
    Object.keys(SIGNALS).map((f) => {
      const d = factorSignalDisplay(SIGNALS, f)
      return [f, d.tone, d.label]
    }),
    [
      ['graduation', 'pass', 'Raises priority'],
      ['degree_progress', 'fail', 'Lowers priority'],
      ['course_requirement', 'review', 'Needs review'],
      ['course_availability', 'unknown', 'Neutral'],
      ['previous_attempts', 'pass', 'Raises priority'],
      ['prerequisite', 'fail', 'Lowers priority'],
      ['progression', 'unknown', 'Neutral'],
    ],
  )
})

test('historical, missing or invalid signals are grey "Not classified", never a guessed colour', () => {
  for (const signals of [undefined, null, 'HIGHER', ['HIGHER'], 1, {}]) {
    assert.deepEqual(factorSignalDisplay(signals, 'graduation'), NOT_CLASSIFIED, JSON.stringify(signals))
  }
  for (const value of ['high', 'Higher', 'PASS', 'MANUAL_REVIEW', '', null, 1, true, {}, 'toString', 'constructor']) {
    assert.deepEqual(factorSignalDisplay({ graduation: value }, 'graduation'), NOT_CLASSIFIED, String(value))
  }
  // A factor missing from otherwise valid signals.
  const partial: Record<string, string> = { ...SIGNALS }
  delete partial.progression
  assert.deepEqual(factorSignalDisplay(partial, 'progression'), NOT_CLASSIFIED)
  assert.equal(factorSignalDisplay(partial, 'graduation').label, 'Raises priority')
  // Inherited keys are not signals.
  assert.deepEqual(factorSignalDisplay(Object.create({ graduation: 'HIGHER' }), 'graduation'), NOT_CLASSIFIED)
  assert.equal(NOT_CLASSIFIED.label, 'Not classified')
  assert.equal(NOT_CLASSIFIED.tone, 'unknown')
})

test('the colour never comes from the explanation text or the overall priority', () => {
  assert.doesNotMatch(UTIL, /reasoning|factor_explanations|priority_level|PRIORITY|\.includes\(|RegExp|\.test\(/)
})

test('green, red and grey are the check-card tones; yellow is added for Raise Capacity only', () => {
  assert.match(PC_CSS, /\.pcr-check\[data-tone='pass'\]/)
  assert.match(PC_CSS, /\.pcr-check\[data-tone='fail'\]/)
  assert.match(CSS, /\.rca-factor\[data-tone='review'\] \{\s*--pcr-fg: #855600;\s*--pcr-bd: #e6cf98;\s*--pcr-tint: #fdf8ec;/)
})
