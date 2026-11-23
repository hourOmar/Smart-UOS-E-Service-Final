import type { ReactNode } from 'react'
import type { EvaluationRun } from '../../services/raiseCapacityReview'
import { NOT_RECORDED, courseLabel } from './format'
import { cleanTechnicalWording, savedText } from '../../utils/raiseCapacityExplanations'

// The eligibility check's three academic checks as colored cards (as on the Course
// Substitution and Course Equivalency review pages). Each card holds the evidence the check
// recorded (a snapshot from evaluation time) and the Eligibility Agent's explanation of that
// check, shown in full. Statuses are exactly those recorded; nothing is recalculated.

type Tone = 'pass' | 'fail' | 'unknown'

const GLYPHS: Record<Tone, string> = { pass: '✓', fail: '✕', unknown: '–' }

function Card({
  id,
  name,
  tone,
  label,
  children,
}: {
  id: string
  name: string
  tone: Tone
  label: string
  children: ReactNode
}) {
  return (
    <section className="pcr-check rca-check" data-tone={tone} aria-labelledby={id}>
      <div className="pcr-check__head">
        <h4 id={id} className="pcr-check__name">
          {name}
        </h4>
        <span className="pcr-check__status">
          <span aria-hidden="true">{GLYPHS[tone]}</span>
          {label}
        </span>
      </div>
      {children}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rca-check__field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

// The agent's explanation of one check, in full as saved (raw field flags in plain words).
function AgentExplanation({ text }: { text: string | undefined }) {
  const body = savedText(text)
  if (!body) return null
  return (
    <p className="rca-check__agent">
      <span className="rca-check__agent-label">Agent’s explanation:</span> {body}
    </p>
  )
}

type PrerequisiteEvidence = NonNullable<EvaluationRun['evidence']>['checks']['prerequisite']
type CourseListKey = 'passed_courses' | 'never_attempted' | 'failed_or_incomplete_courses' | 'unresolved_grade_courses'

const COURSE_STATUS: [CourseListKey, string, Tone][] = [
  ['passed_courses', 'Passed', 'pass'],
  ['never_attempted', 'Never attempted', 'fail'],
  ['failed_or_incomplete_courses', 'Attempted without a passing grade', 'fail'],
  ['unresolved_grade_courses', 'Grade outside the approved policy', 'unknown'],
]

function courseStatus(p: PrerequisiteEvidence, id: number) {
  for (const [key, label, tone] of COURSE_STATUS) {
    if ((p[key] ?? []).map(String).includes(String(id))) return { label, tone }
  }
  return null
}

/** True when the UoS text only names the required courses (it would repeat the list). */
function requirementRepeatsCourses(raw: string, ids: string[], names: Map<string, string>) {
  let rest = raw.toLowerCase()
  for (const id of ids) {
    rest = rest.split(id.toLowerCase()).join(' ')
    const name = names.get(id)
    if (name) rest = rest.split(name.toLowerCase()).join(' ')
  }
  return rest.replace(/\b(and|or|pre|co|requisites?|prerequisites?|corequisites?)\b/g, ' ').replace(/[^a-z0-9]+/g, '') === ''
}

function Prerequisite({ run, names }: { run: EvaluationRun; names: Map<string, string> }) {
  const p = run.evidence!.checks.prerequisite
  const [tone, label]: [Tone, string] = !p.verified
    ? ['unknown', 'NOT VERIFIED']
    : p.satisfied === true
      ? ['pass', 'PASSED']
      : p.satisfied === false
        ? ['fail', 'FAILED']
        : ['unknown', 'UNRESOLVED']
  const groups = p.required_prerequisite_groups ?? []
  const listed = new Set(groups.flat().map(String))
  // Courses with a status that are not in a required group (not expected): still shown.
  const extra = [...new Set(COURSE_STATUS.flatMap(([key]) => p[key] ?? []).filter((id) => !listed.has(String(id))))]
  const allGroups = extra.length > 0 ? [...groups, extra] : groups
  const raw = p.raw_prerequisite_text
  const showRequirement = !raw || groups.length === 0 || !requirementRepeatsCourses(raw, [...listed], names)
  const details = p.details ? cleanTechnicalWording(p.details) : null
  const conditions = p.additional_text_conditions ?? []

  const courseLines = allGroups.map((group) =>
    group.map((id) => ({ id: String(id), text: courseLabel(id, names), status: courseStatus(p, id) })),
  )
  return (
    <Card id="rca-check-prereq" name="Prerequisite" tone={tone} label={label}>
      <dl className="rca-check__fields">
        {showRequirement && (
          <Field label="UoS requirement">
            {raw ?? (p.verified ? 'None listed' : 'Could not be retrieved')}
            {p.is_pre_or_co ? ' (pre- or co-requisite)' : ''}
          </Field>
        )}
        {courseLines.length > 0 && (
          <Field label={courseLines.flat().length > 1 ? 'Required courses' : 'Required course'}>
            {courseLines.map((group, gi) => (
              <div key={gi} className="rca-courses">
                {gi > 0 && <span className="rca-courses__or">{gi === groups.length ? 'Also recorded' : 'or'}</span>}
                <ul className="rca-courses__list">
                  {group.map((course) => (
                    <li key={course.id} className="rca-course">
                      <span className="rca-course__name">{course.text}</span>
                      {course.status && (
                        <span className="rca-course__status" data-tone={course.status.tone}>
                          {course.status.label}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {!showRequirement && p.is_pre_or_co ? <span className="rca-courses__note">Pre- or co-requisite</span> : null}
          </Field>
        )}
        {conditions.length > 0 && <Field label="Other conditions (not evaluated)">{conditions.join('; ')}</Field>}
      </dl>
      {details && <p className="pcr-check__detail">{details}</p>}
      <AgentExplanation text={run.check_explanations?.prerequisite} />
    </Card>
  )
}

const NO_HOURS_RULE = 'No completed-hours rule is configured for this course. This is not a failure.'

function CompletedHours({ run }: { run: EvaluationRun }) {
  const h = run.evidence!.checks.completed_hours
  const [tone, label]: [Tone, string] = !h.applicable
    ? ['unknown', 'NOT APPLICABLE']
    : h.satisfied === true
      ? ['pass', 'PASSED']
      : h.satisfied === false
        ? ['fail', 'FAILED']
        : ['unknown', 'UNRESOLVED']
  const required = `${h.required_hours ?? NOT_RECORDED} hours${h.required_standing ? ` (${h.required_standing})` : ''}`
  const student = h.student_completed_hours == null ? NOT_RECORDED : `${h.student_completed_hours} hours`
  const details = h.details ? cleanTechnicalWording(h.details) : null
  return (
    <Card id="rca-check-hours" name="Completed credit hours" tone={tone} label={label}>
      {h.applicable ? (
        <dl className="rca-check__fields">
          <Field label="Required">{required}</Field>
          <Field label="Student at evaluation">{student}</Field>
        </dl>
      ) : (
        <p className="pcr-check__detail">{NO_HOURS_RULE}</p>
      )}
      {details && <p className="pcr-check__detail">{details}</p>}
      <AgentExplanation text={run.check_explanations?.completed_hours} />
    </Card>
  )
}

function Capacity({ run }: { run: EvaluationRun }) {
  const c = run.evidence!.checks.capacity
  const label = c.satisfied ? 'SPACE AVAILABLE' : 'NO SPACE'
  const figures: [string, number][] = [
    ['Enrolled', c.current_capacity],
    ['Total capacity', c.total_capacity],
    ['Additional capacity', c.additional_capacity],
    ['Maximum allowed', c.maximum_allowed_capacity],
    ['Remaining raise capacity', c.remaining_raise_capacity],
  ]
  return (
    <Card id="rca-check-capacity" name="Section capacity" tone={c.satisfied ? 'pass' : 'fail'} label={label}>
      <dl className="rca-check__fields rca-check__fields--capacity">
        {figures.map(([k, v]) => (
          <Field key={k} label={k}>
            {String(v)}
          </Field>
        ))}
      </dl>
      <AgentExplanation text={run.check_explanations?.capacity} />
    </Card>
  )
}

function EligibilityChecks({ run, names }: { run: EvaluationRun; names: Map<string, string> }) {
  if (!run.evidence?.checks) {
    return <p className="rv-muted">No academic checks were recorded for this evaluation.</p>
  }
  return (
    <div className="rca-checks">
      <Prerequisite run={run} names={names} />
      <CompletedHours run={run} />
      <Capacity run={run} />
    </div>
  )
}

export default EligibilityChecks
