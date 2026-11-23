// The Raise Capacity review page's AI Agent Evaluation: the Prioritization
// Agent's saved result (the one the requests table shows, read only), then the
// Eligibility Agent's recommendation and check cards, then the transcript
// records, all in one section.
// Static checks of the wiring (no browser, backend or database). Run: npm test.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const PAGE = source('../src/pages/AdminRaiseCapacityReview.tsx')
const PANEL = source('../src/components/review/PriorityPanel.tsx')
const HOOK = source('../src/hooks/useRaiseCapacityPriority.ts')
const CELL = source('../src/components/admin/PriorityCell.tsx')
const SERVICE = source('../src/services/raiseCapacityPriority.ts')

test('one AI Agent Evaluation section holds the Prioritization Agent above the Eligibility Agent', () => {
  const section = PAGE.indexOf('AI Agent Evaluation')
  const priority = PAGE.indexOf('<PriorityPanel')
  const eligibility = PAGE.indexOf('<EligibilityPanel')
  const decision = PAGE.indexOf('<DecisionPanel')
  assert.ok(section > -1 && priority > section && eligibility > priority && decision > eligibility)
  // The transcript opens from the Student information card, not from this section.
  assert.doesNotMatch(PAGE, /TranscriptRecords/)
  // Nothing but the priority panel's own props sits between the two agents.
  assert.match(PAGE.slice(priority, eligibility), /^<PriorityPanel[^<]*\/>\s*$/)
  // The separate Academic evidence panel is gone (its contents are in the check cards and transcript).
  assert.doesNotMatch(PAGE, /EvidencePanel|Priority assessment|Eligibility recommendation/)
  assert.match(PANEL, /Prioritization Agent/)
  assert.match(PAGE, /const priority = useRaiseCapacityPriority\(requestId\)/)
})

test('the priority is read from the same endpoint as the requests table; a first check is never started here', () => {
  assert.match(HOOK, /fetchPriorities\(\[requestId\]\)/)
  for (const file of [HOOK, PANEL, PAGE]) {
    assert.doesNotMatch(file, /startAutomaticPriorities|useRaiseCapacityPriorities/)
  }
  assert.match(SERVICE, /export async function fetchPriorities[\s\S]*?`\$\{BASE\}\/priorities\?\$\{query\}`/)
})

test('Re-evaluate re-runs a saved priority (or retries a failed check) only when the backend allows it', () => {
  assert.match(SERVICE, /export async function rerunPriority[\s\S]*?`\$\{BASE\}\/\$\{encodeURIComponent\(requestId\)\}\/priority\/rerun`[\s\S]*?method: 'POST'/)
  assert.match(HOOK, /data\?\.can_rerun \? rerunPriority : data\?\.can_retry \? retryPriority : null/)
  // The button: shown with a result or a failed / running check, disabled while running, for finalized requests,
  // or when the backend does not allow it.
  assert.match(PANEL, /const allowed = Boolean\(data\?\.can_rerun \|\| data\?\.can_retry\) && !finalized/)
  assert.match(PANEL, /<button type="button" className="pcr-rerun" onClick=\{onRerun\} disabled=\{active \|\| !allowed\}/)
  assert.match(PANEL, /\{active \? 'Evaluating…' : 'Re-evaluate'\}/)
  assert.match(PAGE, /onRerun=\{priority\.rerun\}\s+finalized=\{autoRun === false\}/)
  // While any check runs, the state is re-read; the saved result stays on screen meanwhile.
  assert.match(HOOK, /data\?\.state === 'running' \|\| data\?\.last_run\?\.status === 'running'/)
  assert.match(HOOK, /if \(priorityCheckActive\(found \?\? null\)\) poll\(count\)/)
  assert.match(PANEL, /The result below is the previous assessment until the new one is saved\./)
})

test('a failed or discarded re-evaluation keeps the last successful result and says so', () => {
  assert.match(PANEL, /run\?\.trigger === 'rerun' && \(run\.status === 'failed' \|\| run\.status === 'interrupted' \|\| run\.status === 'discarded'\)/)
  assert.match(PANEL, /\{unsuccessfulRerun && <LatestRerun run=\{run\} \/>\}\s*\{data\.priority \? <PriorityCard/)
  assert.match(PANEL, /The\s+result below is the last successful assessment and has not been replaced\./)
  // A failed action is a notice beside the result; a 409 re-reads the current state.
  assert.match(HOOK, /update\(\{ running: false, notice: messageOf\(error\) \}\)/)
  assert.match(HOOK, /error\.status === 409\) void load\(0\)/)
})

test('a read failure is an error with Try again, never "no priority"', () => {
  assert.match(HOOK, /status: 'error',\s+data: null,/)
  assert.match(PANEL, /status === 'error' &&[\s\S]*?The priority assessment could not be loaded\.[\s\S]*?onClick=\{onRetry\}/)
  assert.match(PANEL, /status === 'ready' && \(data \? <PriorityStateView data=\{data\} \/> : <NoAssessment \/>\)/)
})

test('the saved level uses the table\'s labels and pill colours', () => {
  assert.match(SERVICE, /export const PRIORITY_LABELS: Record<PriorityLevel, string>/)
  assert.match(CELL, /import \{ PRIORITY_LABELS \} from '\.\.\/\.\.\/services\/raiseCapacityPriority'/)
  assert.match(PANEL, /import \{\s+PRIORITY_LABELS,[\s\S]*?\} from '\.\.\/\.\.\/services\/raiseCapacityPriority'/)
  assert.doesNotMatch(CELL, /const PRIORITY_LABELS/)
  assert.match(PANEL, /<span className="adm-prio-pill" data-level=\{level\}>\s*\{PRIORITY_LABELS\[level\]\}/)
  // Only a 'saved' state shows a level.
  assert.match(PANEL, /\{data\.priority \? <PriorityCard level=\{data\.priority\} data=\{data\} \/> : <NoAssessment \/>\}/)
  assert.equal(PANEL.match(/<PriorityCard /g)?.length, 1)
})

test('the agent\'s stored reasoning, factors and evidence are shown as stored', () => {
  // The whole saved text, shown directly: no shortening and no expand / collapse control.
  assert.match(PANEL, /const reasoning = savedText\(result\?\.reasoning\)/)
  assert.match(PANEL, /<p className="pcr-summary rca-reasoning">\{reasoning\}<\/p>/)
  assert.match(PANEL, /shown\.map\(\(\[field\]\) => savedText\(factors!\[field\]\)\)/)
  assert.match(PANEL, /<p className="rca-factor__text">\{factorTexts\[index\]\}<\/p>/)
  assert.doesNotMatch(PANEL, /CompactText|compactExplanation|Show full|Show more|Show less/)
  // Key evidence the factor cards do not already state is still listed.
  assert.match(PANEL, /const otherEvidence = uncoveredEvidence\(evidence, factorTexts\)/)
  // The colour and badge come only from the saved signal for that factor, never from the text or overall level.
  const factorCard = PANEL.slice(PANEL.indexOf('const signal = factorSignalDisplay'), PANEL.indexOf('</section>'))
  assert.match(factorCard, /^const signal = factorSignalDisplay\(result\?\.factor_signals, field\)/)
  assert.match(factorCard, /className="pcr-check rca-factor"\s+data-tone=\{signal\.tone\}/)
  assert.match(factorCard, /\{signal\.label\}/)
  assert.match(factorCard, /<p className="rca-factor__text">\{factorTexts\[index\]\}<\/p>/)
  assert.doesNotMatch(factorCard, /level|reasoning|includes\(|match\(|test\(/)
  assert.match(PANEL, /<li key=\{index\}>\{item\}<\/li>/)
  for (const field of ['graduation', 'degree_progress', 'course_requirement', 'course_availability',
    'previous_attempts', 'prerequisite', 'progression']) {
    assert.match(PANEL, new RegExp(`\\['${field}', '`))
    assert.match(SERVICE, new RegExp(`  ${field}: string`))
  }
})

test('the section never offers a decision; its only actions are Try again and Re-evaluate', () => {
  // No repeated advisory notice or ADVISORY label.
  assert.doesNotMatch(PANEL, /Advisory/)
  assert.doesNotMatch(PANEL, /decide_|decideRaiseCapacityRequest|Show full|Show more|Show less/)
  assert.deepEqual(PANEL.match(/onClick=\{\w+\}/g), ['onClick={onRerun}', 'onClick={onRetry}'])
})
