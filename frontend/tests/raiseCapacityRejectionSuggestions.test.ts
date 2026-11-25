// The Raise Capacity Rejection Explanation Agent's suggestions on the review page,
// "Use this reason", and the decision explanation rule (required for a rejection
// only). Pure helper tests plus static checks; no browser, backend or database.
// Run: npm test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { checkDisplay, rejectionSuggestions } from '../src/utils/raiseCapacityEvaluation.ts'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const PAGE = source('../src/pages/AdminRaiseCapacityReview.tsx')
const ELIGIBILITY = source('../src/components/review/EligibilityPanel.tsx')
const DECISION = source('../src/components/review/DecisionPanel.tsx')
const CSS = source('../src/pages/AdminRaiseCapacityReview.css')

const REASONS = [
  { tone: 'supportive', text: 'Supportive text.', addresses_keywords: ['prerequisite_not_passed'], source: 'gemini' },
  { tone: 'formal', text: 'Formal text.', addresses_keywords: ['prerequisite_not_passed'], source: 'gemini' },
  { tone: 'concise', text: 'Concise text.', addresses_keywords: ['prerequisite_not_passed'], source: 'template' },
]

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, run_status: 'completed', trigger: 'rerun', started_at: null, evaluated_at: null,
    recommendation: 'REJECT', reasoning: 'r', check_explanations: null, evidence: null, gemini_status: 'ok',
    gemini_error: null, model: 'm', agent_version: '2.0.0', error_message: null,
    rejection_explanation: {
      status: 'partial_fallback',
      keywords: [{ keyword: 'prerequisite_not_passed', requirement: 'prerequisite', label: 'Prerequisite course not passed',
        policy_basis: 'b', plain_reason: 'p' }],
      suggested_reasons: REASONS,
      conflict_note: '',
    },
    rejection_model: 'rm',
    ...overrides,
  } as never
}

test('three suggestions for a successful REJECT, in formal, concise, supportive order', () => {
  const view = rejectionSuggestions(run())!
  assert.deepEqual(view.reasons.map((r) => [r.tone, r.label, r.text]), [
    ['formal', 'Formal', 'Formal text.'], ['concise', 'Concise', 'Concise text.'], ['supportive', 'Supportive', 'Supportive text.'],
  ])
  assert.deepEqual(view.verifiedReasons, ['Prerequisite course not passed'])
  assert.equal(view.message, null)
})

test('no suggestions for APPROVE, MANUAL_REVIEW, failed runs or runs without a Gemini decision', () => {
  for (const overrides of [
    { recommendation: 'APPROVE' }, { recommendation: 'MANUAL_REVIEW' }, { run_status: 'failed' },
    { run_status: 'interrupted' }, { gemini_status: 'unavailable' },
  ]) {
    assert.equal(rejectionSuggestions(run(overrides)), null, JSON.stringify(overrides))
  }
  assert.equal(rejectionSuggestions(null), null)
})

test('a REJECT recorded without suggestions asks the administrator to write the explanation', () => {
  const view = rejectionSuggestions(run({ rejection_explanation: null }))!
  assert.deepEqual(view.reasons, [])
  assert.match(view.message!, /Write the explanation yourself/)
})

test('template-only suggestions are labelled; a conflict note is kept', () => {
  const view = rejectionSuggestions(run({
    rejection_explanation: { status: 'fallback', keywords: [], suggested_reasons: REASONS, conflict_note: 'Mismatch.' },
  }))!
  assert.match(view.message!, /built only from the verified failures/)
  assert.equal(view.conflictNote, 'Mismatch.')
})

test('2.0.0 check statuses are shown exactly as recorded', () => {
  assert.deepEqual(checkDisplay('SATISFIED'), { tone: 'pass', label: 'PASSED' })
  assert.deepEqual(checkDisplay('NOT_SATISFIED'), { tone: 'fail', label: 'FAILED' })
  assert.deepEqual(checkDisplay('UNRESOLVED'), { tone: 'unknown', label: 'UNRESOLVED' })
  assert.deepEqual(checkDisplay('NOT_APPLICABLE'), { tone: 'unknown', label: 'NOT APPLICABLE' })
  assert.deepEqual(checkDisplay('NOT_EVALUATED'), { tone: 'unknown', label: 'NOT EVALUATED' })
})

test('each suggestion has a Use this reason button that only fills the form', () => {
  assert.match(ELIGIBILITY, /onClick=\{\(\) => onUseReason\(reason\.text\)\}>\s*Use this reason/)
  // The page selects Reject and fills the editable explanation; it never submits.
  assert.match(PAGE, /const applyReason = useCallback\(\(text: string\) => \{\s*setChoice\('reject'\)\s*setExplanation\(text\)\s*\}, \[\]\)/)
  assert.doesNotMatch(PAGE, /decideRaiseCapacityRequest/)
  // Offered only while the request awaits a decision and the form is being edited.
  assert.match(PAGE, /onUseReason=\{decidable && decisionStep === 'form' \? applyReason : null\}/)
  assert.match(PAGE, /const decidable = found\?\.request\.status === 'In Progress'/)
  assert.match(ELIGIBILITY, /Suggestions can be used only while the request is awaiting a decision\./)
  // The decision panel receives the page's state, so the filled explanation stays editable.
  assert.match(PAGE, /choice=\{choice\}\s+onChoiceChange=\{setChoice\}\s+explanation=\{explanation\}\s+onExplanationChange=\{setExplanation\}/)
  assert.match(DECISION, /onChange=\{\(event\) => onExplanationChange\(event\.target\.value\)\}/)
})

test('the suggestions sit below the recommendation and the checks, in the Eligibility panel', () => {
  assert.match(ELIGIBILITY, /<EligibilityChecks run=\{run\} names=\{courseNames\} \/>\s*<\/div>\s*<div className="rca-suggest-row">\s*<Suggestions run=\{run\} onUseReason=\{onUseReason\} \/>/)
  assert.match(CSS, /\.rca-suggest-row \{\s*grid-column: 1 \/ -1;/)
  // The Priority Assessment panel stays above the Eligibility panel.
  assert.ok(PAGE.indexOf('<PriorityPanel') < PAGE.indexOf('<EligibilityPanel'))
})

test('an approval needs no explanation; a rejection still does', () => {
  assert.match(DECISION, /const explanationRequired = choice === 'reject'/)
  assert.match(DECISION, /attempted && explanationRequired && length === 0\s*\? 'Enter an explanation for the rejection\.'/)
  assert.match(DECISION, /\(optional for an approval\)/)
  assert.match(DECISION, /No explanation will be saved with this approval\./)
  // A saved approval without an explanation shows none.
  assert.match(DECISION, /\{d\.explanation\.trim\(\) && \(/)
  // The final decision is still saved only after the explicit confirmation step.
  assert.match(DECISION, /const result = await decideRaiseCapacityRequest\(request\.id, choice, explanation\.trim\(\)\)/)
})
