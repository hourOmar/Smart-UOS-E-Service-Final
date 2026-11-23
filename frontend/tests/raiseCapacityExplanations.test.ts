// Display-only shortening of the Raise Capacity agents' explanations: whole
// sentences of the saved text, uncertainty and conflicts always kept, repeats of
// the card left out, the saved text always available. Run: npm test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import {
  cleanTechnicalWording,
  compactExplanation,
  savedText,
  splitSentences,
  uncoveredEvidence,
} from '../src/utils/raiseCapacityExplanations.ts'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const UTIL = source('../src/utils/raiseCapacityExplanations.ts')
const PRIORITY = source('../src/components/review/PriorityPanel.tsx')
const CHECKS = source('../src/components/review/EligibilityChecks.tsx')
const ELIGIBILITY = source('../src/components/review/EligibilityPanel.tsx')

const CAPACITY_CARD = 'section capacity seats current SPACE AVAILABLE Enrolled 40 Total capacity 40 Additional capacity 3 Maximum allowed 45 Remaining raise capacity 2'

test('the shortening is deterministic presentation logic, never a model call', () => {
  assert.doesNotMatch(UTIL, /fetch\(|callBackend|gemini|supabase|import /i)
  const text = 'One. Two. Three.'
  assert.deepEqual(compactExplanation(text, { maxSentences: 2 }), compactExplanation(text, { maxSentences: 2 }))
})

test('compactExplanation keeps the saved text unchanged in full', () => {
  const saved = 'First point. Second point. Third point. Fourth point.'
  const c = compactExplanation(saved, { maxSentences: 2 })
  assert.equal(c.full, saved)
  assert.equal(c.short, 'First point. Second point.')
  assert.equal(c.shortened, true)
  const short = compactExplanation('Only one sentence.', { maxSentences: 2 })
  assert.deepEqual(short, { short: 'Only one sentence.', full: 'Only one sentence.', shortened: false })
})

test('both agents show every saved explanation in full, with no expand / collapse control', () => {
  for (const [name, file] of [['PriorityPanel', PRIORITY], ['EligibilityPanel', ELIGIBILITY], ['EligibilityChecks', CHECKS]]) {
    assert.doesNotMatch(file, /CompactText|compactExplanation|Show full|Show more|Show less|aria-expanded/, name)
    assert.match(file, /savedText\(/, name)
  }
  // savedText keeps every sentence; it only puts raw flags into plain words.
  const saved = 'First point. Second point (checks.prerequisite.satisfied is null). Third point. Fourth point.'
  assert.equal(savedText(saved), 'First point. Second point (the prerequisite is unresolved). Third point. Fourth point.')
  assert.equal(savedText('  '), '')
  assert.equal(savedText(undefined), '')
})

test('MANUAL_REVIEW reasoning keeps every unresolved conflict and uncertainty', () => {
  const reasoning =
    'The recommendation is MANUAL_REVIEW. The completed-hours rule does not apply. Capacity is available with 2 remaining raise seats. ' +
    'Grade D+ for 1501211 is outside the approved policy, so the prerequisite cannot be confirmed. ' +
    'The UoS page and the transcript conflict on the course ID. Graduation may be affected.'
  const c = compactExplanation(reasoning, { maxSentences: 3 })
  for (const kept of ['MANUAL_REVIEW', 'outside the approved policy', 'conflict on the course ID', 'may be affected']) {
    assert.ok(c.short.includes(kept), kept)
  }
  assert.ok(c.shortened)
})

test('raw flags become the plain words they stand for', () => {
  assert.equal(
    cleanTechnicalWording('The prerequisite failed (checks.prerequisite.verified is true, checks.prerequisite.satisfied is false).'),
    'The prerequisite failed.',
  )
  assert.equal(cleanTechnicalWording('So checks.prerequisite.satisfied is null.'), 'So the prerequisite is unresolved.')
  assert.equal(cleanTechnicalWording('checks.completed_hours.applicable is false here.'), 'The completed-hours rule does not apply here.')
  assert.equal(cleanTechnicalWording('verified: true'), 'Verified')
  assert.equal(cleanTechnicalWording('checks.capacity.satisfied is false.'), 'No additional section capacity is available.')
  assert.equal(cleanTechnicalWording('See checks.capacity.remaining_raise_capacity.'), 'See remaining raise capacity.')
  assert.equal(cleanTechnicalWording('never attempted [1501211, 1501215]; failed []'), 'Never attempted 1501211, 1501215; failed none')
  // Rewording a flag offers the saved text too.
  assert.ok(compactExplanation('It is met (satisfied: true).', { maxSentences: 2 }).shortened)
})

test('a check explanation drops only sentences whose facts the card already shows', () => {
  const capacity =
    'The section currently has 40 students enrolled with a total capacity of 40. ' +
    'An additional capacity of 3 is allowed, up to a maximum of 45, leaving 2 remaining raise seats.'
  const c = compactExplanation(capacity, { maxSentences: 2, shownFacts: CAPACITY_CARD })
  assert.equal(c.short, '')
  assert.equal(c.full, capacity)
  assert.ok(c.shortened)
})

test('a sentence with a new fact, a contradiction or an uncertainty is never dropped', () => {
  for (const sentence of [
    'Only 1 seat remains, not 2.', // a figure the card does not show
    'Additional section capacity is not available.', // contradicts the badge
    'The capacity figures could not be confirmed.', // uncertainty
    'Course 1501211 was attempted with grade F.', // a grade the card does not show
  ]) {
    assert.equal(compactExplanation(sentence, { maxSentences: 2, shownFacts: CAPACITY_CARD + ' 1501211' }).short, sentence, sentence)
  }
})

test('key evidence already stated by a factor card is folded in; unique evidence stays', () => {
  const factors = ['64 of 132 credit hours completed.', 'Expected graduation is more than two terms away.', 'Programming I has a D grade on record.']
  assert.deepEqual(
    uncoveredEvidence(['Completed hours: 64', 'Expected graduation term: 202702', 'Programming I grade: D', 'Graduation term is missing'], factors),
    ['Expected graduation term: 202702', 'Graduation term is missing'],
  )
})

test('sentences split on sentence ends but not on abbreviations or decimals', () => {
  assert.deepEqual(splitSentences('CGPA is 2.5 (e.g. above 2.0). Next one.\nA new line'), [
    'CGPA is 2.5 (e.g. above 2.0).',
    'Next one.',
    'A new line',
  ])
})

test('all seven priority factors and all three eligibility checks remain', () => {
  for (const field of ['graduation', 'degree_progress', 'course_requirement', 'course_availability',
    'previous_attempts', 'prerequisite', 'progression']) {
    assert.match(PRIORITY, new RegExp(`\\['${field}', '`))
  }
  // Every factor with saved text gets a card; shortening never removes one.
  assert.match(PRIORITY, /const shown = factors \? FACTORS\.filter\(\(\[field\]\) => factors\[field\]\) : \[\]/)
  assert.match(CHECKS, /<Prerequisite run=\{run\} names=\{names\} \/>\s+<CompletedHours run=\{run\} \/>\s+<Capacity run=\{run\} \/>/)
  // The prerequisite failure reason and agent explanation stay; the raw UoS text shows when it adds anything.
  assert.match(CHECKS, /\{details && <p className="pcr-check__detail">\{details\}<\/p>\}/)
  assert.match(CHECKS, /<AgentExplanation text=\{run\.check_explanations\?\.prerequisite\} \/>/)
  assert.match(CHECKS, /const showRequirement = !raw \|\| groups\.length === 0 \|\| !requirementRepeatsCourses/)
})
