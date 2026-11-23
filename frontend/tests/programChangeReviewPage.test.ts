// The Program Change review page in a DOM (jsdom): the transcript modal, the
// removed helper texts, and the unchanged evaluation and decision behaviour.
// The real page, hooks and services run; only the Supabase client and fetch
// are replaced, so nothing reaches a database or backend. Rows are synthetic.
// Run: npm test.
import assert from 'node:assert/strict'
import { after, afterEach, before, beforeEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { JSDOM } from 'jsdom'
import { createServer, type ViteDevServer } from 'vite'

// React reads the DOM globals when it is imported, so they are set first.
const dom = new JSDOM('<!doctype html><body></body>', { url: 'http://localhost/' })
for (const name of ['window', 'document', 'navigator', 'HTMLElement', 'Node'] as const) {
  Object.defineProperty(globalThis, name, { value: dom.window[name], configurable: true, writable: true })
}
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
const { StrictMode, act, createElement } = await import('react')
const { createRoot } = await import('react-dom/client')
const { MemoryRouter, Route, Routes } = await import('react-router-dom')

const REQUEST_ID = 'STUD_TEST_000001'
const STUDENT_ID = 'U00000001'

const REMOVED_TEXTS = [
  'Advisory only — the final decision belongs to the administrator.',
  'Nothing is saved until you confirm on the next step.',
  'Your decision differs from the agent’s advisory',
  'Approve the request. Any change to the student’s program is processed separately by the Registrar’s Office.',
  'Decline the request.',
  'Final · recorded under your name',
  'Program Change Eligibility Agent',
]

// -- fakes -----------------------------------------------------------------------------

type Row = Record<string, unknown>
type Recommendation = 'APPROVE' | 'REJECT' | 'REQUIRES_REVIEW'

let tables: Record<string, Row[]>
let failing: Set<string>
let held: Map<string, Promise<void>>
let reads: string[]
let rpcCalls: { name: string; args: Row }[]
let posts: unknown[]
let evaluation: Row

/** Holds every read of `key` until the returned function is called. */
function hold(key: string) {
  let release = () => {}
  held.set(key, new Promise<void>((resolve) => (release = resolve)))
  return () => {
    held.delete(key)
    release()
  }
}

// Only the read methods the page uses exist, so any write would throw.
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
      rows = rows.filter((row) => values.includes(row[column]))
      return builder
    },
    maybeSingle() {
      single = true
      return builder
    },
    async then(resolve: (value: unknown) => void) {
      reads.push(table)
      await held.get(table)
      resolve(failing.has(table)
        ? { data: null, error: { message: 'unavailable' } }
        : { data: single ? (rows[0] ?? null) : rows, error: null })
    },
  }
  return builder
}

const fakeSupabase = {
  from: query,
  auth: {
    getSession: async () => ({ data: { session: { access_token: 'test-token' } } }),
    getUser: async () => ({ data: { user: { id: 'staff-uid' } }, error: null }),
  },
  async rpc(name: string, args: Row) {
    rpcCalls.push({ name, args })
    const status = args.p_decision === 'approve' ? 'Completed' : 'Rejected'
    tables.Request[0].Current_Status = status
    return { data: { status, decision_id: 1 }, error: null }
  },
}
Object.assign(globalThis, { pageTestSupabase: fakeSupabase })

async function fakeFetch(url: unknown, init?: RequestInit) {
  assert.match(String(url), /\/api\/staff\/program-change\//)
  if (init?.method === 'POST') posts.push(JSON.parse(String(init.body)))
  await held.get('evaluation')
  return new Response(JSON.stringify({ evaluation }), { status: 200 })
}

function evaluationState(recommendation: Recommendation | null): Row {
  return {
    request_id: REQUEST_ID,
    request_status: 'In Progress',
    latest_attempt: null,
    in_progress: false,
    run_count: recommendation ? 1 : 0,
    auto_run_eligible: false,
    can_rerun: true,
    current: recommendation && {
      id: 1,
      run_status: 'completed',
      finished_at: '2026-11-20T10:00:00Z',
      recommendation,
      report: 'Issues / Conflicts: None\nOverall Assessment: Synthetic assessment.',
      deterministic_results: {
        matched_courses: [{ course_id: '1501211', course_name: 'Programming I', credit_hours: 3 }],
      },
      eligibility: {
        recorded: true,
        cgpa: { value: 3.1, minimum: 2, passed: true },
        applicable_hours: { value: 3, minimum: 15, passed: false },
        completed_hours: 6,
        recommendation_conflict: false,
      },
    },
  }
}

// -- rendering -------------------------------------------------------------------------

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
      load: (id) =>
        id.endsWith('/src/services/supabase.ts') ? 'export const supabase = globalThis.pageTestSupabase' : null,
    }],
  })
  Page = (await vite.ssrLoadModule('/src/pages/AdminProgramChangeReview.tsx')).default
})

after(async () => {
  globalThis.fetch = originalFetch
  await vite.close()
})

beforeEach(() => {
  tables = {
    Request: [{
      Request_ID: REQUEST_ID, Request_Type: 'Program Change', Request_Date: '2026-11-19',
      Submission_Time: '09:30:00', Current_Status: 'In Progress', Student_ID: STUDENT_ID,
    }],
    Program_Change: [{
      Request_ID: REQUEST_ID, Current_Program_ID: '1502', Current_Program_Name: 'Current Program',
      New_Program_ID: '1501', New_Program_Name: 'Requested Program', Reason: 'A synthetic reason.',
    }],
    Student: [{
      Student_ID: STUDENT_ID, Student_Name: 'Test Student', CGPA: 3.1, Completed_Hours: 36,
      Program_Name: 'Current Program', Program: { College_Name: 'Test College' },
    }],
    Takes: [
      { Student_ID: STUDENT_ID, Course_ID: '1501211', Section_ID: '11', Term: 202502, Grade: 'B' },
      { Student_ID: STUDENT_ID, Course_ID: '1501250', Section_ID: '12', Term: 202601, Grade: null },
      { Student_ID: 'U99999999', Course_ID: '9999999', Section_ID: '99', Term: 202601, Grade: 'A' },
    ],
    Course: [
      { Course_ID: '1501211', Course_Name: 'Programming I', Credit_Hours: 3 },
      { Course_ID: '1501250', Course_Name: 'Networking Fundamentals', Credit_Hours: 4 },
    ],
    Authorized_Staff: [{ Staff_Name: 'Test Admin', Staff_Email: 'admin@example.test' }],
  }
  failing = new Set()
  held = new Map()
  reads = []
  rpcCalls = []
  posts = []
  evaluation = evaluationState('REJECT')
  globalThis.fetch = fakeFetch as typeof fetch
})

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  document.body.replaceChildren()
  document.body.removeAttribute('style')
})

/** Lets promises and the renders they cause finish. */
async function settle() {
  for (let i = 0; i < 5; i += 1) await act(async () => new Promise((resolve) => setTimeout(resolve, 0)))
}

async function open() {
  const container = document.body.appendChild(document.createElement('div'))
  root = createRoot(container)
  const route = createElement(Route, { path: '/review/:requestId', element: createElement(Page) })
  const router = createElement(MemoryRouter, { initialEntries: [`/review/${REQUEST_ID}`] },
    createElement(Routes, null, route))
  await act(async () => root?.render(createElement(StrictMode, null, router)))
  await settle()
}

const $ = <T extends Element = HTMLElement>(selector: string) => document.querySelector<T>(selector)
const all = (selector: string) => [...document.querySelectorAll<HTMLElement>(selector)]
const pageText = () => document.body.textContent ?? ''
const modal = () => $('[role="dialog"][aria-modal="true"]')
const modalText = () => modal()?.textContent ?? ''
const findButton = (label: string) => all('button').find((b) => b.textContent?.trim() === label)
const radio = (value: string) => $<HTMLInputElement>(`input[name="pcr-outcome"][value="${value}"]`)!

async function click(target: HTMLElement | null | undefined) {
  assert.ok(target, 'nothing to click')
  await act(async () => target.click())
  await settle()
}

async function press(key: string, shiftKey = false) {
  const event = new dom.window.KeyboardEvent('keydown', { key, shiftKey, bubbles: true, cancelable: true })
  await act(async () => {
    ;(document.activeElement ?? document.body).dispatchEvent(event)
  })
  await settle()
}

const openTranscript = () => click(findButton('View Student Transcript'))

// -- the button ------------------------------------------------------------------------

test('the button is in the Student information heading, and the Student ID link stays', async () => {
  await open()
  const button = findButton('View Student Transcript')
  assert.ok(button)
  assert.match(button.closest('.rv-panel__head')?.textContent ?? '', /Student information/)
  assert.equal(button.getAttribute('type'), 'button')
  const link = $('.rv-student-link')
  assert.match(link?.getAttribute('href') ?? '', new RegExp(`${STUDENT_ID}$`))
  assert.equal(modal(), null)
})

test('the transcript is read only when the button is used', async () => {
  await open()
  assert.ok(!reads.includes('Takes'))
  await openTranscript()
  assert.ok(reads.includes('Takes'))
})

test('a decided request can still show the transcript', async () => {
  tables.Request[0].Current_Status = 'Rejected'
  await open()
  await openTranscript()
  assert.match(modalText(), /Programming I/)
})

test('no button when the student record cannot be found', async () => {
  tables.Student = []
  await open()
  assert.match(pageText(), /could not be found/)
  assert.equal(findButton('View Student Transcript'), undefined)
})

// -- its content -----------------------------------------------------------------------

test('the modal names the student, the ID and the requested program', async () => {
  await open()
  await openTranscript()
  const context = modal()?.querySelector('dl')?.textContent ?? ''
  for (const value of ['Test Student', STUDENT_ID, 'Requested Program (1501)']) assert.ok(context.includes(value), value)
})

test('each record shows code, name, credit hours and grade under its term, newest first', async () => {
  await open()
  await openTranscript()
  const terms = [...modal()!.querySelectorAll('.sp-term')]
  assert.deepEqual(
    terms.map((term) => ({
      title: term.querySelector('h3')?.firstChild?.textContent,
      cells: [...term.querySelectorAll('tbody td')].map((cell) => cell.textContent),
    })),
    [
      { title: 'Fall 2026', cells: ['1501250', 'Networking Fundamentals', '4', '12', 'No grade recorded'] },
      { title: 'Spring 2026', cells: ['1501211', 'Programming I', '3', '11', 'B'] },
    ],
  )
  assert.doesNotMatch(modalText(), /9999999/, 'another student’s record')
})

test('the records are not presented as complete, official or verified', async () => {
  await open()
  await openTranscript()
  assert.match(modalText(), /Available transcript records/)
  assert.match(modalText(), /may be incomplete and are not an official or verified transcript/)
  // Recorded and transcript hours are not reconciled, so no total is shown here.
  assert.doesNotMatch(modalText(), /Completed credit hours|Total/)
})

// -- loading, empty and error --------------------------------------------------------

test('a loading state shows until the records arrive', async () => {
  const release = hold('Takes')
  await open()
  await openTranscript()
  assert.match(modal()?.querySelector('[role="status"]')?.textContent ?? '', /Loading transcript records/)
  assert.doesNotMatch(modalText(), /No transcript records|could not be loaded/)
  release()
  await settle()
  assert.match(modalText(), /Programming I/)
  assert.doesNotMatch(modalText(), /Loading transcript records/)
})

test('no records is an empty state, not a claim that no courses were completed', async () => {
  tables.Takes = []
  await open()
  await openTranscript()
  assert.match(modalText(), /No transcript records are available in this system for this student/)
  assert.equal(modal()?.querySelector('table, [role="alert"]'), null)
})

for (const table of ['Takes', 'Course']) {
  test(`a failed ${table} read is an error that can be retried`, async () => {
    failing.add(table)
    await open()
    await openTranscript()
    assert.match(modal()?.querySelector('[role="alert"]')?.textContent ?? '', /could not be loaded/)
    assert.doesNotMatch(modalText(), /No transcript records/)
    assert.match(pageText(), /Administrator decision/)

    failing.clear()
    const retry = [...modal()!.querySelectorAll('button')].find((b) => b.textContent === 'Try again')
    retry?.focus()
    await click(retry)
    assert.match(modalText(), /Programming I/)
    assert.ok(modal()?.contains(document.activeElement), 'focus stays in the modal')
  })
}

test('closing while loading is safe, and reopening reads again', async () => {
  const release = hold('Takes')
  await open()
  await openTranscript()
  await click(findButton('Close'))
  release()
  await settle()
  assert.equal(modal(), null)
  await openTranscript()
  assert.match(modalText(), /Programming I/)
})

// -- opening and closing -------------------------------------------------------------

const CLOSERS: Record<string, () => Promise<void>> = {
  'the Close button': () => click(findButton('Close')),
  Escape: () => press('Escape'),
  'the backdrop': () => click($('.pcr-modal__backdrop')),
}

for (const [how, close] of Object.entries(CLOSERS)) {
  test(`${how} closes the modal, keeping the page, selection and focus`, async () => {
    await open()
    await click(radio('approve'))
    const title = $('.pcr-head__title')
    await openTranscript()
    assert.equal(document.activeElement, findButton('Close'))
    assert.equal(document.body.style.overflow, 'hidden')

    await close()
    assert.equal(modal(), null)
    assert.equal(radio('approve').checked, true)
    assert.equal($('.pcr-head__title'), title, 'the page was not remounted')
    assert.equal(document.activeElement, findButton('View Student Transcript'))
    assert.equal(document.body.style.overflow, '')
    assert.equal($('.student')!.style.overflowY, '')
    assert.deepEqual(rpcCalls, [])
  })
}

test('Escape still closes when focus has left the modal', async () => {
  await open()
  await openTranscript()
  ;(document.activeElement as HTMLElement).blur()
  await press('Escape')
  assert.equal(modal(), null)
})

test('Tab and Shift+Tab stay inside the modal', async () => {
  await open()
  await openTranscript()
  const body = modal()!.querySelector<HTMLElement>('.pcr-modal__body')
  await press('Tab', true)
  assert.equal(document.activeElement, body)
  await press('Tab')
  assert.equal(document.activeElement, findButton('Close'))
})

test('an evaluation arriving behind the open modal does not move focus', async () => {
  const release = hold('evaluation')
  await open()
  await openTranscript()
  const body = modal()!.querySelector<HTMLElement>('.pcr-modal__body')!
  body.focus()
  release()
  await settle()
  assert.match(pageText(), /Agent recommendation/)
  assert.equal(document.activeElement, body)
})

test('the confirmation step survives viewing the transcript', async () => {
  await open()
  await click(radio('reject'))
  await click(findButton('Submit Final Decision'))
  await openTranscript()
  await click(findButton('Close'))
  assert.ok(findButton('Confirm rejection'))
  assert.deepEqual(rpcCalls, [])
})

// -- removed texts ---------------------------------------------------------------------

for (const recommendation of ['APPROVE', 'REJECT', 'REQUIRES_REVIEW', null] as const) {
  for (const choice of ['approve', 'reject']) {
    test(`the seven texts are gone (${recommendation ?? 'no evaluation'}, ${choice})`, async () => {
      evaluation = evaluationState(recommendation)
      await open()
      await click(radio(choice))
      for (const removed of REMOVED_TEXTS) assert.ok(!pageText().includes(removed), removed)
      assert.equal($('.pcr-disagree'), null)
    })
  }
}

test('the empty evaluation state keeps its sentence, without the agent name', async () => {
  evaluation = evaluationState(null)
  await open()
  assert.equal(
    $('.pcr-state--empty .pcr-state__body')?.textContent,
    'Run the evaluation to check the student’s CGPA and applicable credit hours against the requested program. ' +
      'Results are recommendations — they don’t change the request status or notify the student.',
  )
})

// -- unchanged evaluation and decision -----------------------------------------------

for (const [recommendation, label] of [
  ['APPROVE', 'APPROVE'], ['REJECT', 'REJECT'], ['REQUIRES_REVIEW', 'REQUIRES REVIEW'],
] as const) {
  test(`the evaluation still shows ${label} with its checks, total, courses and time`, async () => {
    evaluation = evaluationState(recommendation)
    await open()
    assert.equal($('.pcr-ai__title')?.textContent, 'AI Agent Evaluation')
    assert.ok($('.pcr-verdict')?.textContent?.includes(label))
    const checks = all('.pcr-check').map((check) => check.textContent ?? '')
    assert.match(checks[0], /CGPA Requirement.*PASSED.*3\.10.*min 2\.00/)
    assert.match(checks[1], /Applicable Credit Hours.*FAILED.*3.*min 15/)
    assert.equal($('.pcr-total')?.textContent, 'Total completed credits: 6')
    assert.match($('.pcr-courses__table')?.textContent ?? '', /1501211Programming I3/)
    assert.match($('.pcr-ai__generated')?.textContent ?? '', /Last evaluated .*2026/)
  })
}

test('Re-run Evaluation still asks the backend for a re-run', async () => {
  await open()
  assert.deepEqual(posts, [])
  await click(findButton('Re-run Evaluation'))
  assert.deepEqual(posts, [{ rerun: true }])
})

test('the decision is still Approve or Reject only, and needs a choice', async () => {
  await open()
  assert.equal($('.pcr-decision__title')?.textContent, 'Administrator decision')
  assert.deepEqual(all('.pcr-outcome__option').map((option) => option.textContent), ['Approve', 'Reject'])
  assert.equal($('textarea'), null)
  await click(findButton('Submit Final Decision'))
  assert.match(pageText(), /Choose Approve or Reject\./)
  assert.deepEqual(rpcCalls, [])
})

for (const [choice, confirm] of [['approve', 'Confirm approval'], ['reject', 'Confirm rejection']] as const) {
  test(`${choice} is saved only on confirmation, whatever the agent recommended`, async () => {
    evaluation = evaluationState(choice === 'approve' ? 'REJECT' : 'APPROVE')
    await open()
    await click(radio(choice))
    await click(findButton('Submit Final Decision'))
    assert.deepEqual(rpcCalls, [])
    await click(findButton(confirm))
    assert.deepEqual(rpcCalls, [{
      name: 'decide_program_change_request',
      args: { p_request_id: REQUEST_ID, p_decision: choice, p_explanation: null },
    }])
    assert.match(pageText(), /Decision saved/)
  })
}
