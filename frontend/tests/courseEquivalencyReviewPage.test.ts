// The Course Equivalency review page's information cards in a DOM (jsdom):
// layout, the shared transcript modal, and the removed card and field. The
// real page, hooks and services run; only the Supabase client and fetch are
// replaced (the backend answers 503, so the evaluation and syllabi show their
// error states). Rows are synthetic. Run: npm test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, afterEach, before, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'
import { createServer, type ViteDevServer } from 'vite'

const dom = new JSDOM('<!doctype html><body></body>', { url: 'http://localhost/' })
for (const name of ['window', 'document', 'navigator', 'HTMLElement', 'Node'] as const) {
  Object.defineProperty(globalThis, name, { value: dom.window[name], configurable: true, writable: true })
}
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
const { StrictMode, act, createElement } = await import('react')
const { createRoot } = await import('react-dom/client')
const { MemoryRouter, Route, Routes } = await import('react-router-dom')

const REQUEST_ID = 'STUD_TEST_CE_000001'
const PC_REQUEST_ID = 'STUD_TEST_PC_000001'
const STUDENT_ID = 'U00000002'

type Row = Record<string, unknown>
let tables: Record<string, Row[]>
let reads: string[]
/** What GET .../syllabi answers; null = 503 (like the rest of the backend). */
let syllabi: Row | null
/** What GET .../evaluation answers; null = 503. */
let evaluation: Row | null
let rpcCalls: { name: string; args: Row }[]

function evaluationRun(patch: Row = {}): Row {
  return {
    id: 7, run_status: 'completed', trigger: 'first_open', started_at: '2026-11-21T09:00:00Z', finished_at: '2026-11-21T09:02:00Z',
    recommendation: 'REJECT', reasoning: 'Synthetic reasoning.', check_explanations: [], deterministic_results: null, evidence: null,
    evaluated_syllabi: [{ syllabus_id: 'syl-old', side: 'old' }, { syllabus_id: 'syl-new', side: 'new' }],
    outdated: false, outdated_sides: [], rejection_explanation: null, assessment_model: null, rejection_model: null,
    agent_version: '1.0.0', failure_kind: null, error_message: null, ...patch,
  }
}

function evaluationState(patch: Row = {}): Row {
  return {
    request_id: REQUEST_ID, request_status: 'In Progress', details_missing: false, details_missing_message: null,
    syllabi_ready: false, syllabi_missing_message: 'Both syllabi are required before the eligibility check can run.',
    current_syllabi: { old: 'syl-old', new: null }, policy_status: 'draft_thresholds', current: null, latest_attempt: null,
    in_progress: false, run_count: 0, current_syllabus_sources: { old: null, new: null }, first_run_eligible: false,
    auto_run_eligible: false, manual_start_reason: null, can_rerun: false, ...patch,
  }
}

const syllabusRow = (side: 'old' | 'new', patch: Row = {}): Row => ({
  syllabus_id: `syl-${side}`, request_id: REQUEST_ID, side, storage_path: `${REQUEST_ID}/${side}/a.pdf`,
  file_name: 'Calculus I for Engineers - syllabus.pdf', mime_type: 'application/pdf', size_bytes: 122880, sha256: null,
  source: 'staff_upload', uploaded_by_staff_id: 100001, uploaded_at: '2026-11-20T08:00:00Z', registered_at: null,
  is_current: true, superseded_at: null, ...patch,
})

function syllabiState(old: Row | null, next: Row | null, canUpload = true): Row {
  return {
    request_id: REQUEST_ID, request_status: canUpload ? 'In Progress' : 'Rejected', can_upload: canUpload, ready: false,
    sides: { old: { current: old, versions: old ? [old] : [] }, new: { current: next, versions: next ? [next] : [] } },
    limits: { max_bytes: 10485760, max_versions_per_side: 10, allowed_types: [] },
  }
}

function query(table: string) {
  let rows = [...(tables[table] ?? [])]
  let single = false
  const builder = {
    select: () => builder,
    order: () => builder,
    limit: () => builder,
    eq(column: string, value: unknown) {
      rows = rows.filter((row) => !(column in row) || row[column] === value)
      return builder
    },
    in(column: string, values: unknown[]) {
      rows = rows.filter((row) => !(column in row) || values.includes(row[column]))
      return builder
    },
    maybeSingle() {
      single = true
      return builder
    },
    then(resolve: (value: unknown) => void) {
      reads.push(table)
      resolve({ data: single ? (rows[0] ?? null) : rows, error: null })
    },
  }
  return builder
}

Object.assign(globalThis, {
  ceTestSupabase: {
    from: query,
    async rpc(name: string, args: Row) {
      rpcCalls.push({ name, args })
      const status = args.p_decision === 'approve' ? 'Completed' : 'Rejected'
      return { data: { status, decision_id: 1, override: Boolean(args.p_confirm_override) }, error: null }
    },
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'test-token' } } }),
      getUser: async () => ({ data: { user: { id: 'staff-uid' } }, error: null }),
    },
  },
})

const originalFetch = globalThis.fetch
let vite: ViteDevServer
let Page: () => ReturnType<typeof createElement>
let root: ReturnType<typeof createRoot> | null = null

before(async () => {
  vite = await createServer({
    root: fileURLToPath(new URL('..', import.meta.url)),
    configFile: false,
    envDir: false,
    appType: 'custom',
    logLevel: 'error',
    cacheDir: 'node_modules/.vite-page-test',
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    plugins: [{
      name: 'fake-supabase',
      enforce: 'pre',
      load: (id) => (id.endsWith('/src/services/supabase.ts') ? 'export const supabase = globalThis.ceTestSupabase' : null),
    }],
  })
  Page = (await vite.ssrLoadModule('/src/pages/AdminCourseEquivalencyReview.tsx')).default
})

after(async () => {
  globalThis.fetch = originalFetch
  await vite.close()
})

beforeEach(() => {
  tables = {
    Request: [
      { Request_ID: REQUEST_ID, Request_Type: 'Course Equivalency', Request_Date: '2026-11-19', Submission_Time: '09:30:00',
        Current_Status: 'In Progress', Student_ID: STUDENT_ID },
      { Request_ID: PC_REQUEST_ID, Request_Type: 'Program Change', Request_Date: '2026-11-10', Current_Status: 'Completed' },
    ],
    Course_Equivalency: [{
      Request_ID: REQUEST_ID, Old_Course_ID: '1440133', New_Course_ID: '1440131', Reason: 'Same content.',
      Program_Change_Request_ID: PC_REQUEST_ID, Old_Program_Name: 'Old Program', New_Program_Name: 'New Program',
      Plan_Version: 'NP-WEB-2026-10-31', Old_Course_Grade: 'B+', Old_Course_Term: 202501,
    }],
    Course: [
      { Course_ID: '1440133', Course_Name: 'Calculus I for Engineers', Credit_Hours: 3 },
      { Course_ID: '1440131', Course_Name: 'Calculus I', Credit_Hours: 3 },
    ],
    Student: [{ Student_ID: STUDENT_ID, Student_Name: 'Test Student', CGPA: 3.2, Completed_Hours: 40,
      Program_Name: 'Old Program', Program: { College_Name: 'Test College' } }],
    Program_Change: [{ Request_ID: PC_REQUEST_ID, Current_Program_Name: 'Old Program', New_Program_Name: 'New Program' }],
    Takes: [{ Student_ID: STUDENT_ID, Course_ID: '1440133', Section_ID: '21', Term: 202501, Grade: 'B+' }],
    Authorized_Staff: [{ Staff_Name: 'Test Admin', Staff_Email: 'admin@example.test' }],
  }
  reads = []
  syllabi = syllabiState(syllabusRow('old'), null)
  evaluation = null
  rpcCalls = []
  globalThis.fetch = (async (url: unknown, init?: RequestInit) => {
    const path = String(url)
    const get = (init?.method ?? 'GET') === 'GET'
    if (get && path.endsWith('/syllabi') && syllabi) return new Response(JSON.stringify(syllabi), { status: 200 })
    if (get && path.endsWith('/evaluation') && evaluation) return new Response(JSON.stringify({ evaluation }), { status: 200 })
    return new Response('{}', { status: 503 })
  }) as typeof fetch
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  document.body.removeAttribute('style')
})

async function settle() {
  for (let i = 0; i < 5; i += 1) await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
}

async function open() {
  root = createRoot(document.body.appendChild(document.createElement('div')))
  const route = createElement(Route, { path: '/review/:requestId', element: createElement(Page) })
  const router = createElement(MemoryRouter, { initialEntries: [`/review/${REQUEST_ID}`] }, createElement(Routes, null, route))
  await act(async () => root?.render(createElement(StrictMode, null, router)))
  await settle()
}

const $ = (selector: string) => document.querySelector<HTMLElement>(selector)
const panel = (heading: string) =>
  [...document.querySelectorAll<HTMLElement>('section.req-panel')].find((s) => s.querySelector('h2')?.textContent?.trim() === heading)
const labels = (section: HTMLElement | undefined) => [...(section?.querySelectorAll('dt') ?? [])].map((dt) => dt.textContent)
const modal = () => $('[role="dialog"][aria-modal="true"]')
const findButton = (label: string) => [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)

async function click(target: HTMLElement | null | undefined) {
  assert.ok(target, 'nothing to click')
  await act(async () => target.click())
  await settle()
}

// -- layout ----------------------------------------------------------------------------

test('first row: Student information | Request information; then Program Change context full width', async () => {
  await open()
  const page = $('.pcr-page')!
  const firstRow = page.querySelector(':scope > .pcr-row')!
  assert.deepEqual([...firstRow.children].map((s) => s.querySelector('h2')?.textContent?.trim()),
    ['Student information', 'Request information'])
  const context = panel('Program Change context')!
  assert.equal(context.parentElement, page, 'not inside a two-column row')
  assert.equal(firstRow.nextElementSibling, context)
})

test('Request history is gone; the request card is renamed with its fields unchanged', async () => {
  await open()
  const text = document.body.textContent ?? ''
  for (const removed of ['Request history', 'Requested equivalency', 'AI evaluations stored', 'Finalized']) {
    assert.ok(!text.includes(removed), removed)
  }
  assert.deepEqual(labels(panel('Request information')), [
    'Request ID', 'Completed (old) course', 'Old course credit hours', 'Requested (new) course', 'New course credit hours',
    'Grade at submission', 'Submitted',
  ])
  assert.match(panel('Request information')?.textContent ?? '', /1440133 Calculus I for Engineers.*B\+ \(term 202501\).*Same content\./)
})

test('Program Change context drops only the Study plan version field', async () => {
  await open()
  const context = panel('Program Change context')
  assert.deepEqual(labels(context), ['Program Change request', 'From program', 'To program', 'Program Change status'])
  assert.match(context?.textContent ?? '', new RegExp(`${PC_REQUEST_ID}.*Old Program.*New Program.*Approved`))
  assert.equal(context?.querySelector('.req-text__body')?.textContent,
    `Approved Program Change ${PC_REQUEST_ID}: Old Program → New Program.`)
  assert.doesNotMatch(context?.textContent ?? '', /study plan|NP-WEB-2026-10-31/i)
})

test('a legacy request without a linked Program Change keeps its message and has no fields', async () => {
  tables.Course_Equivalency[0].Program_Change_Request_ID = null
  await open()
  const context = panel('Program Change context')
  assert.match(context?.textContent ?? '', /No Program Change was linked when this request was submitted/)
  assert.deepEqual(labels(context), [])
})

// -- transcript ------------------------------------------------------------------------

test('the transcript button sits in the Student information heading; the Student ID link stays', async () => {
  await open()
  const button = findButton('View Student Transcript')
  assert.match(button?.closest('.rv-panel__head')?.textContent ?? '', /Student information/)
  assert.match($('.rv-student-link')?.getAttribute('href') ?? '', new RegExp(`${STUDENT_ID}$`))
  assert.ok(!reads.includes('Takes'), 'the transcript is read only on demand')
})

test('the modal shows the available records and context, then closes back to the same page', async () => {
  await open()
  const title = $('.pcr-head__title')
  const link = $('.rv-student-link')
  await click(findButton('View Student Transcript'))
  const text = modal()?.textContent ?? ''
  for (const value of ['Test Student', STUDENT_ID, 'New Program', '1440133', 'Calculus I for Engineers', 'B+', 'Fall 2025',
    'may be incomplete and are not an official or verified transcript']) {
    assert.ok(text.includes(value), value)
  }

  await click(findButton('Close'))
  assert.equal(modal(), null)
  assert.equal($('.pcr-head__title'), title, 'the page was not remounted')
  assert.equal($('.rv-student-link'), link)
  assert.equal(document.activeElement, findButton('View Student Transcript'))
})

test('Escape closes the modal too', async () => {
  await open()
  await click(findButton('View Student Transcript'))
  await act(async () => {
    document.activeElement?.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  })
  await settle()
  assert.equal(modal(), null)
})

test('no transcript button when the student record is missing', async () => {
  tables.Student = []
  await open()
  assert.equal(findButton('View Student Transcript'), undefined)
})

// -- Program Change context fields ---------------------------------------------------

test('the four context fields share one row on desktop, label above value', async () => {
  await open()
  const fields = panel('Program Change context')!.querySelector('dl')!
  assert.ok(fields.classList.contains('cer-context__fields'))
  assert.deepEqual([...fields.children].map((item) => [...item.children].map((el) => el.tagName)),
    [['DT', 'DD'], ['DT', 'DD'], ['DT', 'DD'], ['DT', 'DD']])
  // Four columns outside the small-screen queries; two, then one, only below 760px / 420px.
  const css = readFileSync(new URL('../src/pages/AdminCourseEquivalencyReview.css', import.meta.url), 'utf8')
  const desktop = css.slice(css.indexOf('.req-fields.cer-context__fields {'), css.indexOf('@media (max-width: 760px)'))
  assert.match(desktop, /grid-template-columns: repeat\(4, minmax\(0, max-content\)\)/)
  assert.match(css, /@media \(max-width: 760px\) \{\s+\.req-fields\.cer-context__fields \{\s+grid-template-columns: repeat\(2/)
})

// -- syllabus cards --------------------------------------------------------------------

const card = (side: 'Old' | 'New') => panel(`${side} Course Syllabus`)!
const inCard = (side: 'Old' | 'New', label: string) =>
  [...card(side).querySelectorAll('button')].find((b) => b.textContent?.replace(/\s+/g, ' ').trim().startsWith(label))

test('an empty side shows the dashed upload area with icon, label, formats and Choose file', async () => {
  await open()
  const zone = card('New').querySelector('.cer-dropzone')
  assert.ok(zone, 'upload area')
  assert.ok(zone.querySelector('.cer-dropzone__icon svg'))
  assert.equal(zone.querySelector('.cer-dropzone__label')?.textContent, 'Upload new syllabus')
  assert.equal(zone.querySelector('.cer-dropzone__rules')?.textContent, 'PDF or DOCX, maximum 10 MB')
  assert.match(zone.textContent ?? '', /No syllabus uploaded yet/)
  const choose = inCard('New', 'Choose file')
  assert.equal(choose?.disabled, false)
  assert.equal(card('New').querySelector('.cer-file'), null)
})

test('the old side gets its own label when empty', async () => {
  syllabi = syllabiState(null, null)
  await open()
  assert.equal(card('Old').querySelector('.cer-dropzone__label')?.textContent, 'Upload old syllabus')
  assert.equal(card('New').querySelector('.cer-dropzone__label')?.textContent, 'Upload new syllabus')
})

test('an uploaded side shows filename, type, size and Download / Replace, compactly', async () => {
  await open()
  const file = card('Old').querySelector('.cer-file')
  assert.ok(file)
  assert.equal(file.querySelector('.cer-file__name')?.textContent, 'Calculus I for Engineers - syllabus.pdf')
  assert.equal(file.querySelector('.cer-file__meta')?.textContent, 'PDF · 120.0 KB')
  // Centered like the upload area: icon, "Uploaded" status, name (full name on hover), muted uploader line.
  assert.ok(file.querySelector('.cer-file__icon svg'))
  assert.equal(file.querySelector('.cer-file__status')?.textContent, '✓ Uploaded')
  assert.equal(file.querySelector('.cer-file__name')?.getAttribute('title'), 'Calculus I for Engineers - syllabus.pdf')
  assert.match(file.querySelector('.cer-file__by')?.textContent ?? '', /Uploaded by Staff ID 100001/)
  // No separate restrictions line; the restrictions stay on the Replace button.
  assert.doesNotMatch(card('Old').textContent ?? '', /Replacement: PDF or DOCX/)
  const replace = inCard('Old', 'Replace')!
  assert.equal(replace.getAttribute('title'), 'PDF or DOCX, maximum 10 MB')
  assert.match(document.getElementById(replace.getAttribute('aria-describedby') ?? '')?.textContent ?? '',
    /PDF or DOCX, maximum 10 MB/)
  assert.match(file.textContent ?? '', /Uploaded by Staff ID 100001/)
  assert.ok(inCard('Old', 'Download'))
  assert.equal(inCard('Old', 'Replace')?.disabled, false)
  assert.equal(card('Old').querySelector('.cer-dropzone'), null)
})

test('no version number or history text, even if more than one version were listed', async () => {
  const older = syllabusRow('old', { syllabus_id: 'syl-old-1', is_current: false })
  const state = syllabiState(syllabusRow('old'), null)
  ;(state.sides as { old: { versions: Row[] } }).old.versions.push(older)
  syllabi = state
  await open()
  const text = card('Old').textContent ?? ''
  assert.doesNotMatch(text, /version \d|earlier kept|history/i)
  assert.ok(inCard('Old', 'Download') && inCard('Old', 'Replace'))
})

test('Choose file and Replace open the same hidden file input as before', async () => {
  await open()
  const opened: string[] = []
  for (const side of ['old', 'new']) {
    const input = document.getElementById(`cer-upload-${side}`) as HTMLInputElement
    assert.equal(input.type, 'file')
    assert.equal(input.accept, '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    input.addEventListener('click', (event) => {
      event.preventDefault()
      opened.push(side)
    })
  }
  await click(inCard('Old', 'Replace'))
  await click(inCard('New', 'Choose file'))
  assert.deepEqual(opened, ['old', 'new'])
})

test('a decided request keeps uploads closed in both designs', async () => {
  syllabi = syllabiState(syllabusRow('old'), null, false)
  await open()
  assert.equal(inCard('Old', 'Replace')?.disabled, true)
  assert.equal(inCard('New', 'Choose file')?.disabled, true)
  assert.ok(card('New').querySelector('.cer-dropzone[data-disabled]'))
  for (const side of ['Old', 'New'] as const) {
    assert.match(card(side).textContent ?? '', /Uploads are closed: the request is no longer In Progress\./)
  }
})

test('a syllabi load error still offers Try again, without an upload area', async () => {
  syllabi = null
  await open()
  assert.ok(inCard('Old', 'Try again'))
  assert.equal(document.querySelector('.cer-dropzone, .cer-file'), null)
})

// -- the rest of the page is still there ----------------------------------------------

test('syllabi, evaluation and decision sections still render below the cards', async () => {
  await open()
  const order = [...document.querySelectorAll('h2')].map((h) => h.textContent?.trim())
  const context = order.indexOf('Program Change context')
  assert.ok(context > -1)
  for (const later of ['AI Agent Evaluation', 'Administrator decision']) {
    assert.ok(order.findIndex((h) => h?.startsWith(later)) > context, later)
  }
  assert.ok(document.querySelectorAll('.pcr-row').length >= 2, 'syllabus row kept')
})

// -- AI Agent Evaluation: waiting for syllabi ------------------------------------------

const aiPanel = () => $('section.pcr-ai')!

test('a missing syllabus shows the centered empty state, naming which one is missing', async () => {
  evaluation = evaluationState()
  await open()
  const waiting = aiPanel().querySelector('.cer-waiting')
  assert.ok(waiting, 'empty state')
  assert.ok(waiting.querySelector('.cer-waiting__icon svg'))
  assert.equal(waiting.querySelector('.cer-waiting__title')?.textContent, 'Waiting for course syllabi')
  assert.equal(waiting.querySelector('.cer-waiting__text')?.textContent,
    'Upload both the old and new course syllabi to run the AI evaluation.')
  assert.deepEqual([...waiting.querySelectorAll('.cer-waiting__pill')].map((p) => [p.getAttribute('data-state'), p.textContent]),
    [['ready', '✓Old syllabus: uploaded'], ['missing', '○New syllabus: missing']])
  // No draft-thresholds note and no large notices.
  assert.doesNotMatch(aiPanel().textContent ?? '', /draft values|have not been confirmed by the department/)
  assert.equal(aiPanel().querySelector('.ier-authenticity, .rv-notice, .cer-waiting__note'), null)
})

test('both syllabi missing are both marked missing', async () => {
  syllabi = syllabiState(null, null)
  evaluation = evaluationState({ current_syllabi: { old: null, new: null } })
  await open()
  assert.deepEqual([...aiPanel().querySelectorAll('.cer-waiting__pill')].map((p) => p.getAttribute('data-state')), ['missing', 'missing'])
})

test('with both syllabi, an evaluation result is shown as before (no empty state)', async () => {
  syllabi = syllabiState(syllabusRow('old'), syllabusRow('new', { syllabus_id: 'syl-new' }))
  evaluation = evaluationState({ syllabi_ready: true, current: evaluationRun(), run_count: 1, can_rerun: true })
  await open()
  assert.equal(aiPanel().querySelector('.cer-waiting'), null)
  assert.equal(aiPanel().querySelector('.ier-authenticity'), null, 'no draft-thresholds note')
  assert.ok(findButton('Re-evaluate'))
})

// -- AI Agent Evaluation: two-column top, safeguards with their explanations ----------

function storedResults(): Row {
  return {
    constraints: {
      minimum_grade: { required: 'C', grade: 'B+', meets: true },
      study_plan: { program_checked: 'Synthetic Program', in_plan: false, note: 'Code note: not in the plan.', program_change: null },
      credit_hours: { old: 3, new: 3, old_covers_new: true },
      transfer_limit: { already_transferred: 6, this_request_adds: 3, total_after: 9, cap_credit_hours: 30,
        college: 'Synthetic College', within_limit: true, note: 'Within the cap.' },
      gpa_impact: 'Recorded as TR.',
    },
    academic_level: { old_level: 1, new_level: 1, old_at_least_new: true },
    old_course: { course_id: '1440133', name: 'Old Course', credit_hours: 3, in_transcript: true, grade: 'B+',
      grade_source: 'transcript', passed: true, term: 202501 },
    new_course: { course_id: '1440131', name: 'New Course', credit_hours: 3 },
    syllabi: { old: { available: true, readable: true, error: null }, new: { available: true, readable: true, error: null } },
    syllabus_request: null,
    similarity: {
      overall_similarity_percent: 67, score_band: 'REVIEW_RANGE', thresholds: { equivalent_min: 80, review_min: 60 },
      components_percent: { topics: 70, learning_outcomes: 55, assessment_structure: 40, credit_hours: 100 },
      verification_ok: true, match_verification: { claimed_total: 12, dropped_total: 2, dropped_percent: 17 },
      credit_hours: { old: 3, new: 3, old_covers_new: true, note: null },
      new_topics_not_covered: ['Synthetic topic'], new_outcomes_not_covered: [],
    },
    text_overlap_percent: 41,
  }
}

// Deliberately out of order, with a repeat and one unknown check, to prove matching is by name.
const CHECK_EXPLANATIONS = [
  { name: 'content_similarity', status: 'FAIL', explanation: 'Agent: similarity is in the review range.' },
  { name: 'academic_level', status: 'PASS', explanation: 'Agent: same academic level.' },
  { name: 'transfer_credit_limit', status: 'PASS', explanation: 'Agent: 9 of 30 credit hours after this request.' },
  { name: 'Minimum Grade', status: 'PASS', explanation: 'Agent: B+ meets the minimum of C.' },
  { name: 'syllabi_available', status: 'PASS', explanation: 'Agent: both syllabi were readable.' },
  { name: 'study_plan', status: 'FAIL', explanation: 'Agent: the course is not in the study plan.' },
  { name: 'study_plan', status: 'FAIL', explanation: 'Agent: the course is not in the study plan.' },   // exact repeat
  { name: 'prerequisites', status: 'N/A', explanation: 'Agent: an extra synthetic check.' },          // unknown name
]

async function openWithResults(runPatch: Row = {}) {
  syllabi = syllabiState(syllabusRow('old'), syllabusRow('new', { syllabus_id: 'syl-new' }))
  evaluation = evaluationState({
    syllabi_ready: true, run_count: 1, can_rerun: true,
    current: evaluationRun({ deterministic_results: storedResults(), check_explanations: CHECK_EXPLANATIONS,
      reasoning: 'Synthetic full reasoning, kept entirely visible.', ...runPatch }),
  })
  await open()
}

const top = () => aiPanel().querySelector<HTMLElement>('.pcr-columns.cer-top')!
const safeguardCards = () => [...top().querySelectorAll<HTMLElement>('.pcr-column--last > .pcr-check')]

test('the top section has two columns: recommendation, then safeguards; no third column or notices', async () => {
  await openWithResults()
  const columns = [...top().children]
  assert.equal(columns.length, 2)
  assert.equal(columns[0].querySelector('.pcr-column__label')?.textContent, 'Agent recommendation')
  assert.equal(columns[1].querySelector('.pcr-column__label')?.textContent, 'Academic safeguards (verified by code)')
  assert.match(columns[0].textContent ?? '', /✕REJECT.*The courses do not appear equivalent\..*Synthetic full reasoning, kept entirely visible\./)
  assert.equal(columns[0].querySelector('.pcr-verdict')?.getAttribute('data-tone'), 'reject')
  const text = aiPanel().textContent ?? ''
  assert.doesNotMatch(text, /Agent’s check explanations|Advisory recommendation only|draft values/)
  assert.equal(aiPanel().querySelector('.pcr-advisory, .ier-authenticity'), null)
  assert.match(aiPanel().querySelector('.pcr-ai__generated')?.textContent ?? '', /^Last evaluated /)
  assert.ok(findButton('Re-evaluate'))
})

test('each safeguard shows its status, value and the agent’s explanation matched by check name', async () => {
  await openWithResults()
  assert.deepEqual(safeguardCards().map((card) => [
    card.querySelector('.pcr-check__name')?.textContent, card.getAttribute('data-tone'),
    card.querySelector('.ier-check__value')?.textContent, card.querySelector('.pcr-check__detail')?.textContent,
  ]), [
    ['Minimum grade', 'pass', 'Grade B+', 'Agent: B+ meets the minimum of C.'],
    ['Requested course in the study plan', 'fail', 'Synthetic Program', 'Agent: the course is not in the study plan.'],
    ['Credit hours', 'pass', '3 vs 3', 'The completed course must have at least the credit hours of the requested course.'],
    ['Transfer credit limit', 'pass', '9 of 30', 'Agent: 9 of 30 credit hours after this request.'],
    ['Academic level', 'pass', '100-level vs 100-level', 'Agent: same academic level.'],
  ])
  // Credit hours had no agent explanation: the safeguard's own description is kept.
  // The repeated study-plan explanation appears once; the unknown check is kept, listed separately.
  assert.equal((aiPanel().textContent ?? '').split('Agent: the course is not in the study plan.').length - 1, 1)
  assert.match(top().querySelector('.cer-other-checks')?.textContent ?? '', /prerequisites · N\/A.*an extra synthetic check/)
  // The two syllabus checks are not in the top section.
  assert.doesNotMatch(top().textContent ?? '', /Syllabi available|Content similarity|both syllabi were readable/)
})

test('no Evidence summary is shown; the suggested explanations follow the similarity directly', async () => {
  await openWithResults({
    recommendation: 'REJECT',
    rejection_explanation: { status: 'ok', keywords: [], notes: [],
      suggested_reasons: [{ tone: 'formal', text: 'Synthetic reason.', addresses_keywords: [] }] },
  })
  const text = aiPanel().textContent ?? ''
  assert.doesNotMatch(text, /Evidence summary|Completed course: |Requested course: |plain word overlap|If approved: /)
  assert.equal(aiPanel().querySelector('details, .cer-evidence'), null)
  const similarity = aiPanel().querySelector('.cer-similarity')!
  assert.ok(similarity.nextElementSibling?.classList.contains('ier-suggest'), 'no gap element left behind')
})

test('the similarity box is centered with its previous width; text inside stays left-aligned', () => {
  const css = readFileSync(new URL('../src/pages/AdminCourseEquivalencyReview.css', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
  const block = css.slice(css.indexOf('.cer-similarity {'), css.indexOf('}', css.indexOf('.cer-similarity {')))
  assert.match(block, /width: calc\(100% - 44px\);/)
  assert.match(block, /margin: 16px auto;/)
  assert.doesNotMatch(block, /text-align/)
  assert.match(css, /@media \(max-width: 640px\) \{[^}]*\.cer-similarity \{\s+width: calc\(100% - 24px\);/)
  assert.doesNotMatch(css, /\.cer-evidence/)
})

test('syllabi available and content similarity appear under the similarity bars with their status', async () => {
  await openWithResults()
  const similarity = aiPanel().querySelector<HTMLElement>('.cer-similarity')!
  const bars = similarity.querySelector('.cer-components')!
  const checks = [...similarity.querySelectorAll<HTMLElement>('.cer-sim-check')]
  assert.ok(bars.compareDocumentPosition(checks[0]) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING, 'below the bars')
  assert.deepEqual(checks.map((c) => [c.querySelector('.pcr-check__name')?.textContent, c.getAttribute('data-tone'),
    c.querySelector('.pcr-check__status')?.textContent, c.querySelector('.pcr-check__detail')?.textContent]), [
    ['Syllabi available', 'pass', '✓PASS', 'Agent: both syllabi were readable.'],
    ['Content similarity', 'fail', '✕FAIL', 'Agent: similarity is in the review range.'],
  ])
  // Similarity values are unchanged.
  assert.match(similarity.querySelector('.cer-similarity__value')?.textContent ?? '', /^67%$/)
  assert.equal(similarity.querySelectorAll('.cer-components__item').length, 4)
})

test('without agent explanations, every safeguard keeps its own description and nothing is invented', async () => {
  await openWithResults({ check_explanations: null })
  assert.equal(safeguardCards()[1].querySelector('.pcr-check__detail')?.textContent, 'Code note: not in the plan.')
  assert.equal(top().querySelector('.cer-other-checks'), null)
  const checks = [...aiPanel().querySelectorAll<HTMLElement>('.cer-sim-check')]
  assert.deepEqual(checks.map((c) => [c.getAttribute('data-tone'), c.querySelector('.pcr-check__detail')?.textContent]),
    [['unknown', 'No explanation was recorded.'], ['unknown', 'No explanation was recorded.']])
})

test('an agent status that differs from the code result is shown, never replacing the code result', async () => {
  await openWithResults({ check_explanations: [{ name: 'minimum_grade', status: 'FAIL', explanation: 'Agent disagrees.' }] })
  const grade = safeguardCards()[0]
  assert.equal(grade.getAttribute('data-tone'), 'pass')
  assert.match(grade.textContent ?? '', /PASSED.*Agent disagrees\..*Agent’s assessment: FAIL/)
})

// -- Administrator decision: always available ------------------------------------------

const decision = () => $('section.cer-decision')!
const option = (value: 'approve' | 'reject') => decision().querySelector<HTMLInputElement>(`input[name="cer-outcome"][value="${value}"]`)!
const note = () => decision().querySelector<HTMLTextAreaElement>('textarea')

async function type(element: HTMLTextAreaElement, value: string) {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value')!.set!
    setter.call(element, value)
    element.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
  await settle()
}

test('the decision panel is usable without any evaluation, with nothing preselected', async () => {
  await open()   // evaluation service unavailable, a syllabus missing
  const text = decision().textContent ?? ''
  assert.match(text, /The AI evaluation could not be loaded\. You can still decide\./)
  assert.equal(option('approve').checked, false)
  assert.equal(option('reject').checked, false)
  assert.deepEqual([...decision().querySelectorAll('.pcr-outcome__option')].map((o) => o.textContent), ['Approve', 'Reject'])
  for (const removed of ['Final · recorded under your name', 'Nothing is saved until you confirm on the next step.',
    'Record an administrative approval', 'Decline the request.']) {
    assert.ok(!text.includes(removed), removed)
  }
  assert.equal(note(), null, 'no explanation before a choice')
  // No academic-record information box in the form.
  assert.equal(decision().querySelector('form .cer-limitation'), null)
  assert.ok(!text.includes('Academic-record integration is not available yet.'))
  assert.ok(findButton('Submit Final Decision'))
  await click(findButton('Submit Final Decision'))
  assert.match(decision().textContent ?? '', /Choose Approve or Reject\./)
  assert.deepEqual(rpcCalls, [])
})

test('Approve needs no explanation and is saved without an evaluation after confirmation', async () => {
  await open()
  await click(option('approve'))
  assert.equal(note(), null, 'no explanation field for Approve')
  await click(findButton('Submit Final Decision'))
  assert.match(decision().textContent ?? '', /recorded without an AI evaluation/)
  assert.deepEqual(rpcCalls, [], 'nothing saved before the confirmation')
  await click(findButton('Confirm approval'))
  assert.deepEqual(rpcCalls, [{
    name: 'decide_course_equivalency_request',
    args: { p_request_id: REQUEST_ID, p_decision: 'approve', p_explanation: '', p_evaluation_id: null, p_confirm_override: false },
  }])
  assert.match(decision().textContent ?? '', /Decision saved: Approved/)
})

test('Reject shows a required explanation; empty is refused, filled is saved', async () => {
  await open()
  await click(option('reject'))
  const field = note()
  assert.ok(field, 'explanation field for Reject')
  assert.equal(field.required, true)
  assert.match(decision().querySelector(`label[for="${field.id}"]`)?.textContent ?? '', /Explanation to student/)
  await click(findButton('Submit Final Decision'))
  assert.match(decision().textContent ?? '', /Enter an explanation for the student\./)
  assert.equal(findButton('Confirm rejection'), undefined)

  await type(note()!, '  The syllabi cover different topics.  ')
  await click(findButton('Submit Final Decision'))
  assert.match(decision().querySelector('.pcr-confirm__explanation')?.textContent ?? '', /The syllabi cover different topics\./)
  await click(findButton('Confirm rejection'))
  assert.deepEqual(rpcCalls[0].args, {
    p_request_id: REQUEST_ID, p_decision: 'reject', p_explanation: 'The syllabi cover different topics.',
    p_evaluation_id: null, p_confirm_override: false,
  })
})

test('text typed for a rejection is not sent with an approval', async () => {
  await open()
  await click(option('reject'))
  await type(note()!, 'Draft reason')
  await click(option('approve'))
  assert.equal(note(), null)
  await click(findButton('Submit Final Decision'))
  await click(findButton('Confirm approval'))
  assert.equal(rpcCalls[0].args.p_explanation, '')
})

test('a running evaluation does not block the decision; it is decided without it', async () => {
  syllabi = syllabiState(syllabusRow('old'), syllabusRow('new', { syllabus_id: 'syl-new' }))
  evaluation = evaluationState({ syllabi_ready: true, in_progress: true, run_count: 1,
    latest_attempt: evaluationRun({ id: 8, run_status: 'running', recommendation: null, finished_at: null }) })
  await open()
  assert.match(decision().textContent ?? '', /An AI evaluation is running\. You can wait for it, or decide now/)
  await click(option('approve'))
  await click(findButton('Submit Final Decision'))
  await click(findButton('Confirm approval'))
  assert.equal(rpcCalls[0].args.p_evaluation_id, null)
})

test('a current evaluation is sent (not repeated in the decision); overriding it still needs confirmation', async () => {
  syllabi = syllabiState(syllabusRow('old'), syllabusRow('new', { syllabus_id: 'syl-new' }))
  evaluation = evaluationState({ syllabi_ready: true, current: evaluationRun(), run_count: 1, can_rerun: true })
  await open()
  // The recommendation stays in the AI Agent Evaluation section only.
  assert.match(aiPanel().querySelector('.pcr-verdict')?.textContent ?? '', /REJECT/)
  assert.equal(decision().querySelector('.pcr-verdict'), null)
  assert.doesNotMatch(decision().textContent ?? '', /Agent recommendation|Evaluation #|current syllabi|do not appear equivalent/)
  await click(option('approve'))   // against REJECT
  await click(findButton('Submit Final Decision'))
  assert.match(decision().textContent ?? '', /Confirm that you are overriding the agent’s recommendation\./)
  assert.equal(findButton('Confirm approval'), undefined)
  await click(decision().querySelector<HTMLInputElement>('.cer-override__confirm input'))
  await click(findButton('Submit Final Decision'))
  await click(findButton('Confirm approval'))
  assert.deepEqual(rpcCalls[0].args, {
    p_request_id: REQUEST_ID, p_decision: 'approve', p_explanation: '', p_evaluation_id: 7, p_confirm_override: true,
  })
})

test('an outdated evaluation is not sent and asks for no override', async () => {
  syllabi = syllabiState(syllabusRow('old'), syllabusRow('new', { syllabus_id: 'syl-new-2' }))
  evaluation = evaluationState({ syllabi_ready: true, current: evaluationRun({ outdated: true, outdated_sides: ['new'] }), run_count: 1 })
  await open()
  assert.match(decision().textContent ?? '', /its recommendation does not reflect the current files and is not used/)
  await click(option('approve'))
  await click(findButton('Submit Final Decision'))
  await click(findButton('Confirm approval'))
  assert.equal(rpcCalls[0].args.p_evaluation_id, null)
  assert.equal(rpcCalls[0].args.p_confirm_override, false)
})

test('a recorded approval without an explanation shows no empty explanation', async () => {
  tables.Request[0].Current_Status = 'Completed'
  tables.Decision = [{ Request_ID: REQUEST_ID, Decision_ID: 3, Decision_Type: 'Course Equivalency Approved', Decision_Comment: '',
    Decision_Date: '2026-11-22 10:00:00', Staff_ID: 100001, Authorized_Staff: { Staff_Name: 'Test Admin' } }]
  await open()
  const recorded = decision().querySelector('.pcr-recorded')
  assert.ok(recorded)
  assert.match(recorded.textContent ?? '', /Approved/)
  assert.equal(recorded.querySelector('.pcr-recorded__note'), null)
})

// -- "Use this reason": suggested explanations fill the rejection ---------------------

const SUGGESTED = {
  formal: 'Synthetic formal reason: the requested course is not in your study plan.',
  concise: 'Synthetic concise reason: not in the study plan.',
  supportive: 'Synthetic supportive reason: please contact your advisor about the study plan.',
}

async function openWithSuggestions(requestStatus = 'In Progress') {
  tables.Request[0].Current_Status = requestStatus
  await openWithResults({
    recommendation: 'REJECT',
    rejection_explanation: {
      status: 'ok', notes: [],
      keywords: [{ id: 'k1', type: 'verified', description: 'Not in the study plan.' }],
      suggested_reasons: Object.entries(SUGGESTED).map(([tone, text]) => ({ tone, text, addresses_keywords: ['k1'] })),
    },
  })
}

const useReason = (label: string) =>
  [...aiPanel().querySelectorAll('button')].find((b) => b.textContent === `Use this reason (${label})`)

test('each of the three suggestion cards has a "Use this reason" button', async () => {
  await openWithSuggestions()
  const items = [...aiPanel().querySelectorAll<HTMLElement>('.ier-suggest__item')]
  assert.deepEqual(items.map((i) => [i.querySelector('.ier-suggest__tone')?.textContent, i.querySelector('button')?.textContent]), [
    ['Formal', 'Use this reason (Formal)'], ['Concise', 'Use this reason (Concise)'], ['Supportive', 'Use this reason (Supportive)'],
  ])
  // Heading kept; agent label, verified reasons and model/version line removed.
  assert.ok(aiPanel().querySelector('#cer-suggest-title'))
  assert.doesNotMatch(aiPanel().textContent ?? '', /Verified reasons|Rejection Explanation Agent ·|staff only|edit before use|Eligibility model|explanation model|agent 1\.0\.0/)
  assert.equal(aiPanel().querySelector('.ier-suggest__agent, .ier-meta'), null)
  assert.equal(option('reject').checked, false, 'nothing preselected before a suggestion is used')
})

for (const [label, key] of [['Formal', 'formal'], ['Concise', 'concise'], ['Supportive', 'supportive']] as const) {
  test(`"Use this reason" (${label}) selects Reject and fills the explanation, without submitting`, async () => {
    await openWithSuggestions()
    await click(useReason(label))
    assert.equal(option('reject').checked, true)
    assert.equal(option('approve').checked, false)
    assert.equal(note()?.value, SUGGESTED[key])
    assert.equal(findButton('Confirm rejection'), undefined, 'still on the form')
    assert.deepEqual(rpcCalls, [])
  })
}

test('the inserted text can be edited, and another suggestion replaces it', async () => {
  await openWithSuggestions()
  await click(useReason('Formal'))
  await type(note()!, `${SUGGESTED.formal} Edited by the administrator.`)
  assert.equal(note()?.value, `${SUGGESTED.formal} Edited by the administrator.`)
  await click(useReason('Concise'))
  assert.equal(note()?.value, SUGGESTED.concise)
  assert.deepEqual(rpcCalls, [])
})

test('the edited suggestion is what the decision sends, only after Submit and confirmation', async () => {
  await openWithSuggestions()
  await click(useReason('Supportive'))
  await type(note()!, `${SUGGESTED.supportive} Edited.`)
  await click(findButton('Submit Final Decision'))
  assert.match(decision().querySelector('.pcr-confirm__explanation')?.textContent ?? '', /Synthetic supportive reason.*Edited\./)
  // While confirming, suggestions cannot change the text being confirmed.
  assert.equal(useReason('Formal'), undefined)
  assert.match(aiPanel().textContent ?? '', /Suggestions can be used only while the request is awaiting a decision\./)
  assert.deepEqual(rpcCalls, [])
  await click(findButton('Confirm rejection'))
  assert.equal(rpcCalls.length, 1)
  assert.equal(rpcCalls[0].args.p_decision, 'reject')
  assert.equal(rpcCalls[0].args.p_explanation, `${SUGGESTED.supportive} Edited.`)
})

test('a custom explanation works without any suggestion', async () => {
  await openWithSuggestions()
  await click(option('reject'))
  assert.equal(note()?.value, '')
  await type(note()!, 'A custom explanation written by the administrator.')
  await click(findButton('Submit Final Decision'))
  await click(findButton('Confirm rejection'))
  assert.equal(rpcCalls[0].args.p_explanation, 'A custom explanation written by the administrator.')
})

test('approval is unchanged: switching to Approve hides the text and sends none', async () => {
  await openWithSuggestions()
  await click(useReason('Formal'))
  await click(option('approve'))
  assert.equal(note(), null)
  await click(findButton('Submit Final Decision'))
  // Approving against the agent's REJECT still needs the override confirmation.
  assert.match(decision().textContent ?? '', /Confirm that you are overriding the agent’s recommendation\./)
  await click(decision().querySelector<HTMLInputElement>('.cer-override__confirm input'))
  await click(findButton('Submit Final Decision'))
  await click(findButton('Confirm approval'))
  assert.equal(rpcCalls[0].args.p_decision, 'approve')
  assert.equal(rpcCalls[0].args.p_explanation, '')
  assert.equal(rpcCalls[0].args.p_confirm_override, true)
})

test('a decided request offers no "Use this reason"', async () => {
  await openWithSuggestions('Rejected')
  assert.equal(useReason('Formal'), undefined)
  assert.match(aiPanel().textContent ?? '', /Suggestions can be used only while the request is awaiting a decision\./)
})
