// The Incomplete Exam staff review page: the saved-evaluation summary, the GET
// path, and static guarantees: opening the page never runs the agents, runs
// and decisions come only from explicit staff clicks, proof documents are
// opened only through the private download, and nothing handles the token.
// Run: npm test (no browser, backend or database).
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import {
  RECOMMENDATION_LABELS,
  incompleteExamEvaluationPath,
  savedEvaluationStatus,
  yesNo,
  type IncompleteExamEvaluationState,
  type IncompleteExamRun,
} from '../src/utils/incompleteExamEvaluation.ts'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const SERVICE = source('../src/services/incompleteExamReview.ts')
const PAGE = source('../src/pages/AdminIncompleteExamReview.tsx')
const UTILS = source('../src/utils/incompleteExamEvaluation.ts')
const APP = source('../src/App.tsx')

function state(overrides: Partial<IncompleteExamEvaluationState> = {}): IncompleteExamEvaluationState {
  return {
    request_id: 'STUD_INCRQ_INC2_900052', request_status: 'In Progress', details_missing: false,
    details_missing_message: null, current: null, latest_attempt: null, in_progress: false, run_count: 0,
    auto_run_eligible: true, can_rerun: true, ...overrides,
  }
}

function run(overrides: Partial<IncompleteExamRun> = {}): IncompleteExamRun {
  return {
    id: 1, run_status: 'completed', trigger: 'first_open', started_at: '2026-11-07T10:00:00+00:00',
    finished_at: '2026-11-07T10:00:20+00:00', recommendation: 'MANUAL_REVIEW', recommendation_conflict: false,
    assessment_model: 'gemini-3.6-flash', rejection_model: null, agent_version: '1.2.0', failure_kind: null,
    error_message: null, ...overrides,
  }
}

// -- the GET path ------------------------------------------------------------------

test('the evaluation path is the staff GET route, with the ID encoded', () => {
  assert.equal(incompleteExamEvaluationPath('STUD_INCRQ_INC2_900052'),
    '/api/staff/incomplete-exam/STUD_INCRQ_INC2_900052/evaluation')
  assert.equal(incompleteExamEvaluationPath('a/b c'), '/api/staff/incomplete-exam/a%2Fb%20c/evaluation')
})

// -- saved evaluation summary -----------------------------------------------------------

test('never evaluated and eligible: says so, and that this page does not start one', () => {
  const saved = savedEvaluationStatus(state())
  assert.equal(saved.tone, 'none')
  assert.equal(saved.label, 'Not evaluated yet')
  assert.match(saved.detail, /does not start one/)
})

test('not eligible (finalized) and never evaluated', () => {
  const saved = savedEvaluationStatus(state({ request_status: 'Completed', auto_run_eligible: false, can_rerun: false }))
  assert.match(saved.detail, /none can start/)
})

test('details missing comes first and shows the backend message', () => {
  const saved = savedEvaluationStatus(state({ details_missing: true, details_missing_message: 'No details.',
    auto_run_eligible: false, can_rerun: false }))
  assert.deepEqual(saved, { tone: 'missing', label: 'Details missing', detail: 'No details.' })
})

test('a running evaluation', () => {
  assert.equal(savedEvaluationStatus(state({ in_progress: true, run_count: 1 })).tone, 'running')
})

test('a completed evaluation shows the advisory recommendation', () => {
  for (const [value, label] of Object.entries(RECOMMENDATION_LABELS)) {
    const saved = savedEvaluationStatus(state({ current: run({ recommendation: value as IncompleteExamRun['recommendation'] }),
      run_count: 1, auto_run_eligible: false }))
    assert.equal(saved.label, `Evaluated · ${label}`)
    assert.match(saved.detail, /decision stays with staff/)
  }
})

test('a failed later attempt keeps the last successful result', () => {
  const saved = savedEvaluationStatus(state({ current: run(), latest_attempt: run({ id: 2, run_status: 'failed',
    recommendation: null, failure_kind: 'technical', error_message: 'Gemini was unavailable.' }), run_count: 2 }))
  assert.equal(saved.tone, 'evaluated')
  assert.match(saved.detail, /later attempt failed/)
})

test('only a failed attempt: shows its safe message, never a recommendation', () => {
  const saved = savedEvaluationStatus(state({ latest_attempt: run({ run_status: 'failed', recommendation: null,
    failure_kind: 'technical', error_message: 'The AI service (Gemini) was unavailable.' }), run_count: 1,
  auto_run_eligible: false }))
  assert.deepEqual(saved, { tone: 'failed', label: 'Last attempt failed', detail: 'The AI service (Gemini) was unavailable.' })
  const interrupted = savedEvaluationStatus(state({ latest_attempt: run({ run_status: 'interrupted', recommendation: null,
    failure_kind: 'interrupted', error_message: null }), run_count: 1, auto_run_eligible: false }))
  assert.equal(interrupted.label, 'Last attempt interrupted')
})

test('yes / no labels', () => {
  assert.equal(yesNo(true), 'Yes')
  assert.equal(yesNo(false), 'No')
})

// -- service guarantees ------------------------------------------------------------------

test('the saved-state read is a GET that never runs the agents', () => {
  const start = SERVICE.indexOf('export async function fetchIncompleteExamEvaluation')
  // The function body only (up to its closing brace), not the next function's doc comment.
  const end = SERVICE.indexOf('\n}\n', start)
  assert.ok(start >= 0 && end > start)
  const read = SERVICE.slice(start, end)
  assert.match(read, /incompleteExamEvaluationPath\(requestId\)/)
  assert.match(read, /method: 'GET'/)
  assert.doesNotMatch(read, /POST|evaluationsPath|rerun/)
})

test('the service never handles the token, logs, stores or makes public links', () => {
  for (const forbidden of [/\bfetch\(/, /access_token/, /getSession/, /console\./, /localStorage/, /sessionStorage/,
    /setInterval/, /setTimeout/, /createSignedUrl/, /getPublicUrl/, /\.upload\(/, /\.remove\(/, /service_role/i]) {
    assert.doesNotMatch(SERVICE, forbidden)
  }
})

// -- review page guarantees -------------------------------------------------------------------

const EVALUATION_PANEL = source('../src/components/incompleteExamReview/EvaluationPanel.tsx')
const DECISION_PANEL = source('../src/components/incompleteExamReview/DecisionPanel.tsx')
const PROOFS = source('../src/components/incompleteExamReview/ProofDocuments.tsx')
const UI = { PAGE, EVALUATION_PANEL, DECISION_PANEL, PROOFS }

test('the page and its panels never touch the token, Supabase, storage or timers directly', () => {
  for (const [name, text] of Object.entries(UI)) {
    for (const forbidden of [/\bsupabase\b/, /\bfetch\(/, /access_token/, /getSession/, /console\./, /localStorage/,
      /sessionStorage/, /setInterval/, /setTimeout/, /createSignedUrl/, /getPublicUrl/, /callBackend/,
      /requestIncompleteExamEvaluation/, /service_role/i]) {
      assert.doesNotMatch(text, forbidden, `${name} must not match ${forbidden}`)
    }
  }
})

test('opening the page never runs the agents: runs come only from Run Evaluation / Re-evaluate clicks', () => {
  // No effect in the page or the evaluation panel; the only effect in the
  // proof panel releases local URLs on unmount.
  assert.doesNotMatch(PAGE, /useEffect/)
  assert.doesNotMatch(EVALUATION_PANEL, /useEffect/)
  assert.equal(PROOFS.match(/useEffect\(/g)?.length, 1)
  assert.match(PROOFS, /for \(const revoke of list\.splice\(0\)\) revoke\(\)/)
  // Every call of onRun is a click handler (onRetry is only the failed
  // attempt's Re-evaluate button).
  const calls = EVALUATION_PANEL.match(/onRun\(/g)?.length ?? 0
  const clicks = EVALUATION_PANEL.match(/on(Click|Retry)=\{\(\) => onRun\((true|false)\)\}/g)?.length ?? 0
  assert.ok(calls > 0 && calls === clicks, `${calls} onRun calls, ${clicks} in click handlers`)
  assert.match(EVALUATION_PANEL, /<button type="button" className="pcr-primary" onClick=\{onRetry\}>\s+Re-evaluate/)
  assert.match(EVALUATION_PANEL, /\{firstAllowed && \(\s+<button type="button" className="pcr-primary" onClick=\{\(\) => onRun\(false\)\}>\s+Run Evaluation/)
  assert.match(EVALUATION_PANEL, /disabled=\{!rerunAllowed\}/)
  assert.match(EVALUATION_PANEL, /'Re-evaluate'/)
  assert.match(PAGE, /onRun=\{evaluation\.run\}/)
})

test('technical failures are shown apart from recommendations, and conflicts are flagged', () => {
  assert.match(EVALUATION_PANEL, /Technical failure: the evaluation couldn’t be completed/)
  assert.match(EVALUATION_PANEL, /No recommendation was recorded/)
  assert.match(EVALUATION_PANEL, /Technical failure: the latest re-evaluation/)
  assert.match(EVALUATION_PANEL, /\{run\.recommendation_conflict && \(\s+<p className="pcr-conflict" role="alert">/)
})

test('proof documents open only on a click, through the private download', () => {
  assert.match(PROOFS, /await openProofDocument\(requestId, path\)/)
  assert.equal(PROOFS.match(/openProofDocument\(/g)?.length, 1)
  assert.match(PROOFS, /onClick=\{\(\) => void handle\(path, 'open'\)\}/)
  assert.match(PROOFS, /onClick=\{\(\) => void handle\(path, 'download'\)\}/)
  assert.match(PROOFS, /tab\.opener = null/)
  assert.match(PROOFS, /revokers\.current\.push\(proof\.revoke\)/)
})

test('decisions are saved only after confirmation, through the decision service', () => {
  assert.equal(DECISION_PANEL.match(/decideIncompleteExamRequest\(/g)?.length, 1)
  assert.match(DECISION_PANEL, /const save = async \(\) => \{\s+if \(!choice \|\| savingRef\.current\) return/)
  assert.match(DECISION_PANEL, /onClick=\{\(\) => void save\(\)\}/)
  assert.match(DECISION_PANEL, /if \(!choice \|\| decisionExplanationError\(choice, explanation, true\) !== null\) return/)
  // Only a rejection sends its explanation; an approval sends none.
  assert.match(DECISION_PANEL, /decideIncompleteExamRequest\(request\.id, choice, explanationToSend\(choice, explanation\)\)/)
  // The confirmation step is unchanged; it shows the explanation for a rejection only.
  assert.match(DECISION_PANEL, /\{needsExplanation && \(\s+<div className="pcr-confirm__explanation">/)
  // Missing details or a finalized request: no form at all.
  assert.match(DECISION_PANEL, /\{finalized \? \(\s+<RecordedDecision record=\{record\} \/>\s+\) : !request\.details \? \(/)
})

test('"Use this reason" selects Reject and fills the editable explanation; nothing is saved', () => {
  assert.match(EVALUATION_PANEL, /onClick=\{\(\) => onUseReason\(reason\.text\)\}/)
  const apply = PAGE.slice(PAGE.indexOf('const applyReason'), PAGE.indexOf('}, [])', PAGE.indexOf('const applyReason')))
  // A suggested reason is a rejection explanation: Reject is selected so its field is shown.
  assert.match(apply, /setChoice\('reject'\)\s+setExplanation\(text\)/)
  assert.doesNotMatch(apply, /decide|save|setChoice\('approve'\)/)
  assert.match(PAGE, /choice=\{choice\}\s+onChoiceChange=\{setChoice\}/)
  assert.match(PAGE, /onUseReason=\{decidable && decisionStep === 'form' \? applyReason : null\}/)
  assert.match(PAGE, /const decidable = Boolean\(found && found\.request\.status === 'In Progress' && found\.request\.details\)/)
  assert.match(DECISION_PANEL, /value=\{explanation\}/)
})

test('the explanation field is shown, and required, for Reject only', () => {
  // Shown only while Reject is selected (switching to Approve hides it).
  assert.match(DECISION_PANEL, /const needsExplanation = explanationRequired\(choice\)/)
  assert.match(DECISION_PANEL, /\{needsExplanation && \(\s+<div className="pcr-note">/)
  assert.match(DECISION_PANEL, /const noteError = decisionExplanationError\(choice, explanation, attempted\)/)
  // The outcome is the page's (so switching updates the field at once).
  assert.match(DECISION_PANEL, /onChange=\{\(\) => \{\s+onChoiceChange\(option\.value\)/)
  assert.doesNotMatch(DECISION_PANEL, /useState<DecisionChoice/)
  // The approve option no longer promises an explanation; a recorded approval without one shows none.
  assert.match(DECISION_PANEL, /description: 'Approve the Incomplete Exam request\. The student is notified\.'/)
  assert.match(DECISION_PANEL, /\{d\.explanation\.trim\(\) && <p className="pcr-recorded__note">\{d\.explanation\}<\/p>\}/)
})

test('the review link is enabled for Incomplete Exam with the back-navigation origin', () => {
  const REVIEW_ACTION = source('../src/components/admin/ReviewAction.tsx')
  const ADMIN_PATHS = source('../src/utils/adminPaths.ts')
  assert.match(ADMIN_PATHS, /'Incomplete Exam': incompleteExamReviewPath/)
  assert.match(REVIEW_ACTION, /reviewPathFor\(requestType, requestId\)/)
  assert.match(REVIEW_ACTION, /origin === 'all-requests' \? \{ from: origin, search: returnSearch \} : \{ from: origin \}/)
  assert.match(REVIEW_ACTION, /state=\{state\}/)
  assert.match(PAGE, /origin === 'dashboard'\s+\? \{ to: ADMIN_HOME_PATH, label: 'Admin home' \}\s+: \{ to: adminTypePath\('incomplete-exam'\), label: 'Incomplete Exam requests' \}/)
})

test('students see the final Incomplete Exam decision and explanation', () => {
  const STUDENT_PAGE = source('../src/pages/StudentRequestDetails.tsx')
  assert.match(STUDENT_PAGE, /const showIncompleteExamDecision = request\.type === INCOMPLETE_EXAM && decided/)
  assert.match(STUDENT_PAGE, /useIncompleteExamDecision\(request\.id, showIncompleteExamDecision\)/)
  assert.match(STUDENT_PAGE, /explanation=\{incompleteExam\.decision\?\.explanation\}/)
})

test('"Approved" for an Incomplete Exam comes only from a recorded approval decision', () => {
  const STUDENT_PAGE = source('../src/pages/StudentRequestDetails.tsx')
  // Student: the decision function's approve AND a decision record (its
  // decision alone may come from the final status).
  assert.match(STUDENT_PAGE, /const approvalRecorded =\s+incompleteExam\.decision\?\.decision === 'approve' && incompleteExam\.decision\.hasDecisionRecord/)
  assert.match(STUDENT_PAGE, /approvalRecorded=\{approvalRecorded\}/)
  assert.match(STUDENT_PAGE, /decisionHeading\(request, approvalRecorded\)/)
  assert.match(STUDENT_PAGE, /statusLabel\(request\.status, request\.type, approvalRecorded\)/)
  const STUDENT_DECISION = source('../src/utils/incompleteExamStudentDecision.ts')
  assert.match(STUDENT_DECISION, /if \(!body \|\| body\.has_decision_record !== true\) return null/)
  assert.match(source('../src/services/incompleteExamStudent.ts'), /return toIncompleteExamDecisionView\(data\)/)
  // Staff: the loaded 'Incomplete Exam Approved' decision record.
  assert.match(PAGE, /return record\.decision\?\.choice === 'approve'/)
  assert.equal(PAGE.match(/approvalRecorded=\{approvalRecorded\((record|found)\)\}/g)?.length, 2)
  assert.match(PAGE, /statusLabel\(history\.status, request\.type, approvalRecorded\(record\)\)/)
  // A finalized request without a decision record keeps its stored status.
  assert.match(DECISION_PANEL, /This request is \{statusLabel\(record\.request\.status, record\.request\.type\)\}/)
})

test('removed text: authenticity banner, advisory note, agent name, model/version footer and decision sub-lines', () => {
  for (const removed of [
    'does not verify that they are authentic',
    'Advisory only — the final decision belongs to the administrator.',
    'Incomplete Exam Eligibility Agent',
    'Eligibility model',
    'ier-meta',
    'ier-authenticity',
    'pcr-ai__agent',
    'assessment_model',
    'agent_version',
  ]) {
    assert.ok(!EVALUATION_PANEL.includes(removed), removed)
  }
  for (const removed of ['Final · recorded under your name', 'Nothing is saved until you confirm on the next step.']) {
    assert.ok(!DECISION_PANEL.includes(removed), removed)
  }
  // Kept: the heading, last evaluated date, Re-evaluate, and the decision's confirmation step.
  assert.match(EVALUATION_PANEL, />\s*AI Agent Evaluation\s*</)
  assert.match(EVALUATION_PANEL, /Last evaluated \{lastEvaluated\}/)
  assert.match(EVALUATION_PANEL, /onClick=\{\(\) => onRun\(true\)\}\s+disabled=\{!rerunAllowed\}/)
  assert.match(DECISION_PANEL, />\s*Submit Final Decision\s*</)
  assert.match(DECISION_PANEL, /className="pcr-confirm" role="alertdialog"/)
})

test('two columns as on Course Equivalency: recommendation left, checks with their explanations right', () => {
  const CSS = source('../src/pages/AdminIncompleteExamReview.css')
  const results = EVALUATION_PANEL.slice(EVALUATION_PANEL.indexOf('function Results'), EVALUATION_PANEL.indexOf('function FailedAttempt'))
  assert.equal(results.match(/className="pcr-column(?: pcr-column--last)?"/g)?.length, 2)
  assert.ok(results.indexOf('Agent recommendation') < results.indexOf('Verified checks (database)'))
  assert.doesNotMatch(results, /Agent’s check explanations|ier-explanations/)
  // Each card: the status badge, the verified value and detail, then the agent's explanation below a divider.
  const card = results.slice(results.indexOf('cards.map('))
  assert.ok(card.indexOf('pcr-check__status') < card.indexOf('check.detail'))
  assert.ok(card.indexOf('check.detail') < card.indexOf('Agent’s explanation:'))
  assert.match(card, /data-tone=\{check\?\.tone \?\? 'unknown'\}/)
  assert.match(CSS, /\.pcr-columns\.ier-top \{\s*grid-template-columns: minmax\(0, 2fr\) minmax\(0, 3fr\);/)
  assert.match(CSS, /@media \(max-width: 860px\) \{\s*\.pcr-columns\.ier-top \{\s*grid-template-columns: minmax\(0, 1fr\);/)
  assert.match(CSS, /\.ier-check__agent \{[^}]*border-top: 1px solid var\(--pcr-bd\);/)
})

test('the stated reason and an identical description are shown once', () => {
  assert.match(PAGE, /const description = distinctDescription\(d\?\.reason, request\.summary\)/)
  assert.match(PAGE, /\{description && \(/)
})

test('the temporary live-test code is gone', () => {
  assert.equal(existsSync(new URL('../src/services/incompleteExamTestRun.ts', import.meta.url)), false)
  for (const removed of [/incompleteExamTestRun/, /requestTestEvaluation/, /TEST_EVALUATION/, /isTestEvaluationRequest/,
    /canRunTestEvaluation/, /Run Test Evaluation/, /Test evaluation/, /Confirm and run/]) {
    assert.doesNotMatch(PAGE, removed)
    assert.doesNotMatch(UTILS, removed)
  }
})

test('the page is staff-only and every existing admin route is kept', () => {
  assert.match(APP, /path="\/admin\/requests\/incomplete-exam\/:requestId"\s+element=\{\s+<ProtectedRoute requiredRole="admin">\s+<AdminIncompleteExamReview \/>/)
  for (const route of ['/admin', '/admin/requests/raise-capacity/:requestId',
    '/admin/requests/program-change/:requestId', '/admin/requests/:typeId']) {
    assert.ok(APP.includes(`path="${route}"`), `route ${route} is kept`)
  }
})
