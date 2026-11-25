// The Raise Capacity review layout: the Eligibility Agent's check cards (with the
// evidence that used to be in "Academic evidence"), the transcript modal opened
// from the Student information card, and the Administrator Decision. Static checks; no browser, backend or database.
// Run: npm test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const PAGE = source('../src/pages/AdminRaiseCapacityReview.tsx')
const ELIGIBILITY = source('../src/components/review/EligibilityPanel.tsx')
const CHECKS = source('../src/components/review/EligibilityChecks.tsx')
const MODAL = source('../src/components/programChangeReview/TranscriptModal.tsx')
const PROGRAM_CHANGE = source('../src/pages/AdminProgramChangeReview.tsx')
const DECISION = source('../src/components/review/DecisionPanel.tsx')
const CSS = source('../src/pages/AdminRaiseCapacityReview.css')

test('the Eligibility Agent shows a coloured recommendation and keeps its re-evaluation', () => {
  assert.match(ELIGIBILITY, /Eligibility Agent/)
  for (const [key, tone, label] of [['APPROVE', 'approve', 'APPROVE'], ['REJECT', 'reject', 'REJECT'], ['MANUAL_REVIEW', 'review', 'MANUAL REVIEW']]) {
    assert.match(ELIGIBILITY, new RegExp(`${key}: \\{ tone: '${tone}', glyph: '.', label: '${label}' \\}`))
  }
  assert.match(ELIGIBILITY, /<span className="pcr-verdict" data-tone=\{rec\.tone\}>/)
  assert.match(ELIGIBILITY, /onClick=\{onRerun\} disabled=\{active\}/)
  assert.match(PAGE, /onRerun=\{evaluation\.rerun\}/)
  // No advisory label or note, and no model / version line.
  assert.doesNotMatch(ELIGIBILITY, /Advisory|advisory-note|model_name|model_version|RunMeta/)
})

test('each academic check is a coloured card with its evidence and the agent explanation', () => {
  for (const [name, key] of [['Prerequisite', 'prerequisite'], ['Completed credit hours', 'completed_hours'], ['Section capacity', 'capacity']]) {
    assert.match(CHECKS, new RegExp(`name="${name}"`))
    assert.match(CHECKS, new RegExp(`run\\.check_explanations\\?\\.${key}`))
  }
  assert.match(CHECKS, /className="pcr-check rca-check" data-tone=\{tone\}/)
  // Recorded statuses are kept, including not-verified / not-applicable / unresolved.
  for (const label of ['NOT VERIFIED', 'PASSED', 'FAILED', 'UNRESOLVED', 'NOT APPLICABLE', 'SPACE AVAILABLE', 'NO SPACE']) {
    assert.ok(CHECKS.includes(`'${label}'`), label)
  }
  // The evidence formerly in "Academic evidence": prerequisite courses and attempts, capacity figures, source.
  for (const field of ['Other conditions (not evaluated)', 'Student at evaluation', 'UoS requirement']) {
    assert.ok(CHECKS.includes(`label="${field}"`), field)
  }
  // Each required course is listed once, with its own attempt status.
  for (const status of ['Passed', 'Never attempted', 'Attempted without a passing grade', 'Grade outside the approved policy']) {
    assert.ok(CHECKS.includes(`, '${status}', '`), status)
  }
  for (const figure of ['Enrolled', 'Total capacity', 'Additional capacity', 'Maximum allowed', 'Remaining raise capacity']) {
    assert.ok(CHECKS.includes(`['${figure}', c.`), figure)
  }
  // The source link and its scope note are not shown on the prerequisite card.
  assert.doesNotMatch(CHECKS, /source_url|source_scope|rca-check__source|Computer Science degree page/)
})

test('evaluation-time evidence is marked as a snapshot', () => {
  assert.match(ELIGIBILITY, /<span className="rv-snapshot__tag">Snapshot<\/span>/)
})

test('Student information is on the left, Request information on the right, without a Current record badge', () => {
  assert.match(PAGE, /<div className="rv-grid">\s*<StudentPanel record=\{found\} \/>\s*<RequestPanel record=\{found\} \/>\s*<\/div>/)
  assert.match(PAGE, /className="req-panel__title rv-panel__title">\s*Student information\s*<\/h2>/)
  assert.doesNotMatch(PAGE, /Current record/)
})

test('the transcript notice is hidden on Raise Capacity only', () => {
  // Raise Capacity turns it off; the notice and its aria-describedby are left out entirely.
  assert.match(PAGE, /showNote=\{false\}/)
  assert.match(MODAL, /showNote = true,/)
  assert.match(MODAL, /aria-describedby=\{showNote \? 'pcr-transcript-note' : undefined\}/)
  assert.match(MODAL, /\{showNote && \(\s*<p id="pcr-transcript-note" className="pcr-modal__note">/)
  // Program Change and Course Equivalency keep it (they never pass showNote).
  assert.doesNotMatch(PROGRAM_CHANGE, /showNote/)
  assert.doesNotMatch(source('../src/pages/AdminCourseEquivalencyReview.tsx'), /showNote/)
})

test('the transcript opens from the Student information card, as on Program Change', () => {
  const student = PAGE.slice(PAGE.indexOf('function StudentPanel'), PAGE.indexOf('function AdminRaiseCapacityReview'))
  const pcStudent = PROGRAM_CHANGE.slice(PROGRAM_CHANGE.indexOf('function StudentPanel'), PROGRAM_CHANGE.indexOf('function RequestPanel'))
  // The same header button (top right of the card head), modal and focus return as Program Change.
  const button =
    /<div className="rv-panel__head">[\s\S]*?<button\s+ref=\{transcriptButton\}\s+type="button"\s+className="pcr-transcript-button"\s+aria-haspopup="dialog"\s+onClick=\{\(\) => setTranscriptOpen\(true\)\}\s*>\s*View Student Transcript\s*<\/button>\s*\)\}\s*<\/div>/
  assert.match(student, button)
  assert.match(pcStudent, button)
  assert.match(PAGE, /import TranscriptModal from '\.\.\/components\/programChangeReview\/TranscriptModal'/)
  assert.match(student, /\{s && transcriptOpen && \(\s*<TranscriptModal\s+studentId=\{s\.id\}\s+studentName=\{s\.name\}/)
  assert.match(student, /onClose=\{closeTranscript\}\s+returnFocusRef=\{transcriptButton\}/)
  // The modal shows every record (course, term, section, grade) and closes on Close, Escape or the backdrop.
  assert.match(MODAL, /<TranscriptTerms\s+entries=\{entries\}/)
  assert.match(MODAL, /event\.key === 'Escape'/)
  assert.match(MODAL, /className="pcr-modal__backdrop" aria-hidden="true" onClick=\{onClose\}/)
  // Program Change and Course Equivalency keep their Requested program row; Raise Capacity shows the course instead.
  assert.match(MODAL, /\{requestedProgram !== undefined && \(/)
  assert.match(student, /requestedCourse=\{/)
  assert.doesNotMatch(student, /requestedProgram/)
  // The separate Transcript Records section is gone; the other student fields are unchanged.
  assert.doesNotMatch(PAGE, /TranscriptRecords|rca-transcript/)
  for (const field of ['Name', 'Student ID', 'Email', 'Program', 'College', 'CGPA', 'Completed credit hours', 'Expected graduation term']) {
    assert.ok(student.includes(`label="${field}"`), field)
  }
})

test('the Administrator Decision keeps its validation and confirmation step', () => {
  assert.match(DECISION, />\s*Administrator Decision\s*</)
  assert.match(DECISION, />\s*Submit Final Decision\s*</)
  assert.match(DECISION, /Explanation to student/)
  assert.doesNotMatch(DECISION, /Staff decision|Your decision is final|Nothing is saved until you confirm/)
  // An explanation is required for a rejection only (approval without one: database update 04).
  assert.match(DECISION, /if \(!choice \|\| \(choice === 'reject' && length === 0\) \|\| length > MAX_EXPLANATION\) return\s+setStep\('confirm'\)/)
  assert.match(DECISION, /decideRaiseCapacityRequest\(request\.id, choice, explanation\.trim\(\)\)/)
  assert.match(DECISION, /Confirm \$\{choice === 'approve' \? 'approval' : 'rejection'\}/)
})

test('the new styles are Raise Capacity only (rca-) and narrow screens get one column', () => {
  const added = CSS.slice(CSS.indexOf('/* Raise Capacity only (rca-)'))
  for (const selector of added.match(/^[.][^{,\n]+/gm) ?? []) assert.ok(selector.includes('.rca-'), selector)
  // The two agent columns stack on narrow screens (as Course Equivalency's do at 860px).
  assert.match(added, /@media \(max-width: 860px\) \{\s*\.rca-columns\.pcr-columns \{\s*grid-template-columns: minmax\(0, 1fr\);/)
})

test('each agent uses the Course Equivalency two-column layout: result left, cards stacked right', () => {
  const PRIORITY = source('../src/components/review/PriorityPanel.tsx')
  const CE_CSS = source('../src/pages/AdminCourseEquivalencyReview.css')
  const added = CSS.slice(CSS.indexOf('/* Raise Capacity only (rca-)'))
  // Same proportions as Course Equivalency's result row.
  assert.match(CE_CSS, /\.pcr-columns\.cer-top \{\s*grid-template-columns: minmax\(0, 2fr\) minmax\(0, 3fr\);/)
  assert.match(added, /\.rca-columns\.pcr-columns \{\s*grid-template-columns: minmax\(0, 2fr\) minmax\(0, 3fr\);/)
  // Cards are stacked, not a grid.
  assert.match(added, /\.rca-factors,\n\.rca-checks \{\s*display: flex;\s*flex-direction: column;/)
  for (const [panel, left, right, cards] of [
    [PRIORITY, 'Priority result', 'Priority factors', 'rca-factors'],
    [ELIGIBILITY, 'Agent recommendation', 'Eligibility checks', 'EligibilityChecks'],
  ]) {
    const start = panel.indexOf('<div className="pcr-columns rca-columns">')
    const split = panel.indexOf('<div className="pcr-column pcr-column--last">')
    assert.ok(start > -1 && split > start, right)
    const leftCol = panel.slice(start, split)
    const rightCol = panel.slice(split)
    assert.ok(leftCol.includes(`<span className="pcr-column__label">${left}</span>`), left)
    assert.match(leftCol, /<p className="pcr-summary rca-reasoning">/)
    assert.ok(rightCol.includes(`<span className="pcr-column__label">${right}</span>`), right)
    assert.ok(rightCol.includes(cards), cards)
  }
  // Badges stay in the left column; the eligibility snapshot note sits with the check cards.
  assert.match(PRIORITY.slice(PRIORITY.indexOf('pcr-columns rca-columns'), PRIORITY.indexOf('pcr-column--last')), /adm-prio-pill/)
  assert.match(ELIGIBILITY.slice(ELIGIBILITY.indexOf('pcr-columns rca-columns'), ELIGIBILITY.indexOf('pcr-column--last')), /pcr-verdict/)
  assert.match(ELIGIBILITY.slice(ELIGIBILITY.indexOf('pcr-column--last')), /\{run\.evidence\?\.checks && <Snapshot run=\{run\} \/>\}\s*<EligibilityChecks/)
  // Unique key evidence is still listed.
  assert.match(PRIORITY, /Other key evidence/)
})
