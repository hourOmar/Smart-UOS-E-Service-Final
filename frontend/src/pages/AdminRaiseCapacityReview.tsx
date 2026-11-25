import { useCallback, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import useStaffIdentity from '../hooks/useStaffIdentity'
import useReviewRecord from '../hooks/useReviewRecord'
import useEligibilityEvaluation from '../hooks/useEligibilityEvaluation'
import useCourseNames from '../hooks/useCourseNames'
import useRaiseCapacityPriority from '../hooks/useRaiseCapacityPriority'
import { formatDate } from '../services/studentRequests'
import type { DecisionChoice, PrerequisiteCheckV2, ReviewRecord } from '../services/raiseCapacityReview'
import {
  ADMIN_HOME_PATH,
  ADMIN_MENU_ITEMS,
  adminTypePath,
  allRequestsReturnPath,
  studentProfilePath,
  type ReviewOrigin,
} from '../utils/adminPaths'
import StudentLayout from '../components/student/StudentLayout'
import ReviewBreadcrumb from '../components/admin/ReviewBreadcrumb'
import RequestStatusBadge from '../components/requests/RequestStatusBadge'
import EligibilityPanel from '../components/review/EligibilityPanel'
import PriorityPanel from '../components/review/PriorityPanel'
import TranscriptModal from '../components/programChangeReview/TranscriptModal'
import DecisionPanel from '../components/review/DecisionPanel'
import { NOT_RECORDED } from '../components/review/format'
import '../components/requests/Requests.css'
import './AdminDashboard.css'
import './AdminProgramChangeReview.css'
import './AdminRaiseCapacityReview.css'

function Field({ label, value, wide = false }: { label: string; value: ReactNode; wide?: boolean }) {
  const missing = value === null || value === undefined || value === ''
  return (
    <div className={`req-fields__item${wide ? ' req-fields__item--wide' : ''}`}>
      <dt>{label}</dt>
      <dd className={missing ? 'rv-missing' : undefined}>{missing ? NOT_RECORDED : value}</dd>
    </div>
  )
}

function RequestPanel({ record }: { record: ReviewRecord }) {
  const { request } = record
  const d = request.details
  return (
    <section className="req-panel rv-panel" aria-labelledby="rv-request-title">
      <h2 id="rv-request-title" className="req-panel__title">
        Request information
      </h2>
      <div className="req-panel__body">
        {!d && (
          <p className="rv-notice" role="alert">
            This request has no Raise Capacity details (course, section, term and justification are
            missing), so it cannot be evaluated.
          </p>
        )}
        <dl className="req-fields">
          <Field label="Request ID" value={<span className="adm-mono">{request.id}</span>} />
          <Field label="Status" value={<RequestStatusBadge status={request.status} requestType={request.type} />} />
          <Field
            label="Submitted"
            value={request.date ? `${formatDate(request.date)}${request.time ? `, ${request.time.slice(0, 5)}` : ''}` : null}
          />
          <Field label="Course" value={d ? [d.courseId, d.courseName].filter(Boolean).join(' ') : null} />
          <Field label="Section" value={d?.sectionId} />
          <Field label="Term" value={d ? String(d.term) : null} />
          <Field label="Summary" value={request.summary} wide />
        </dl>
        <div className="req-text">
          <span className="req-text__label">Student justification</span>
          {d?.justification ? (
            <p className="req-text__body">{d.justification}</p>
          ) : (
            <p className="rv-missing">{NOT_RECORDED}</p>
          )}
        </div>
      </div>
    </section>
  )
}

// The transcript opens in the same modal as on the Program Change review page.
function StudentPanel({ record }: { record: ReviewRecord }) {
  const s = record.student
  const d = record.request.details
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const transcriptButton = useRef<HTMLButtonElement>(null)
  const closeTranscript = useCallback(() => setTranscriptOpen(false), [])
  return (
    <section className="req-panel rv-panel" aria-labelledby="rv-student-title">
      <div className="rv-panel__head">
        <h2 id="rv-student-title" className="req-panel__title rv-panel__title">
          Student information
        </h2>
        {s && (
          <button
            ref={transcriptButton}
            type="button"
            className="pcr-transcript-button"
            aria-haspopup="dialog"
            onClick={() => setTranscriptOpen(true)}
          >
            View Student Transcript
          </button>
        )}
      </div>
      {s && transcriptOpen && (
        <TranscriptModal
          studentId={s.id}
          studentName={s.name}
          requestedCourse={d ? [d.courseId, d.courseName].filter(Boolean).join(' ') || null : null}
          showNote={false}
          onClose={closeTranscript}
          returnFocusRef={transcriptButton}
        />
      )}
      <div className="req-panel__body">
        {s ? (
          <dl className="req-fields">
            <Field label="Name" value={s.name} />
            <Field
              label="Student ID"
              value={
                <Link to={studentProfilePath(s.id)} className="adm-mono rv-student-link">
                  {s.id}
                  <span className="student-visually-hidden"> (open student profile)</span>
                </Link>
              }
            />
            <Field label="Email" value={s.email} />
            <Field label="Program" value={s.program} />
            <Field label="College" value={s.college} />
            <Field label="CGPA" value={s.cgpa == null ? null : s.cgpa.toFixed(2)} />
            <Field label="Completed credit hours" value={s.completedHours == null ? null : String(s.completedHours)} />
            <Field
              label="Expected graduation term"
              value={s.expectedGraduationTerm == null ? null : String(s.expectedGraduationTerm)}
            />
          </dl>
        ) : (
          <p className="rv-notice" role="alert">
            The student record ({record.request.studentId}) could not be found.
          </p>
        )}
      </div>
    </section>
  )
}

// Staff review of one Raise Capacity request: request and student details
// (read directly, so they show even if the eligibility service fails), the AI
// Agent Evaluation (the Prioritization Agent's saved priority and the
// Eligibility Agent's recommendation with its check cards, a snapshot from
// evaluation time; the transcript opens from the Student information card), and
// the administrator's decision (database function, signed-in staff session).
function AdminRaiseCapacityReview() {
  const { requestId } = useParams()
  const location = useLocation()
  const identity = useStaffIdentity()
  const record = useReviewRecord(requestId)
  // Automatic first evaluation only for In Progress requests; while the
  // request is still loading (or could not be loaded) nothing runs.
  const recordFound = record.status === 'ready' && record.result?.kind === 'found' ? record.result.record : null
  const autoRun = recordFound ? recordFound.request.status === 'In Progress' : null
  const evaluation = useEligibilityEvaluation(requestId, autoRun)
  // The saved priority, as in the requests table; staff can re-evaluate it here
  // (In Progress requests only). It never changes the request or its decision.
  const priority = useRaiseCapacityPriority(requestId)

  const origin = (location.state as { from?: ReviewOrigin } | null)?.from
  const allRequests = allRequestsReturnPath(location.state)
  const back = allRequests
    ? { to: allRequests, label: 'All Requests' }
    : origin === 'dashboard'
      ? { to: ADMIN_HOME_PATH, label: 'Admin home' }
      : { to: adminTypePath('raise-capacity'), label: 'Raise Capacity requests' }

  const found = record.status === 'ready' && record.result?.kind === 'found' ? record.result.record : null
  const shownRun = evaluation.data?.current ?? null
  const prerequisite = shownRun?.evidence?.checks.prerequisite
  const groupIds = [
    // Runs before agent 2.0.0: the parsed prerequisite groups.
    ...(prerequisite?.required_prerequisite_groups ?? []).flat().map(String),
    // Agent 2.0.0+: the course conditions of the complete requirement.
    ...((prerequisite as unknown as PrerequisiteCheckV2 | undefined)?.course_conditions ?? [])
      .map((c) => c.course_id ?? '')
      .filter(Boolean),
  ]
  const names = useCourseNames(groupIds)

  // The administrator's decision form state, held here so a suggested rejection
  // reason can select Reject and fill the explanation ("Use this reason"). It
  // never submits: the administrator edits, submits and confirms.
  const [choice, setChoice] = useState<DecisionChoice | null>(null)
  const [explanation, setExplanation] = useState('')
  const [decisionStep, setDecisionStep] = useState<'form' | 'confirm'>('form')
  const decidable = found?.request.status === 'In Progress' && Boolean(found?.request.details)
  const applyReason = useCallback((text: string) => {
    setChoice('reject')
    setExplanation(text)
  }, [])

  return (
    <StudentLayout profile={identity} solidHeader homePath={ADMIN_HOME_PATH} menuItems={ADMIN_MENU_ITEMS}>
      <div className="adm-page rv-page">
        <ReviewBreadcrumb typeId="raise-capacity" />

        {record.status === 'ready' && record.result?.kind === 'not-found' && (
          <div className="req-state">
            <span className="req-state__icon" aria-hidden="true">○</span>
            <h1 className="req-state__title">Request not found</h1>
            <p className="req-state__body">There is no request with the ID {requestId}.</p>
            <Link to={back.to} className="req-view">Back to {back.label}</Link>
          </div>
        )}

        {record.status === 'ready' && record.result?.kind === 'other-type' && (
          <div className="req-state">
            <span className="req-state__icon" aria-hidden="true">○</span>
            <h1 className="req-state__title">Not a Raise Capacity request</h1>
            <p className="req-state__body">
              {requestId} is a {record.result.type} request. Review is available for Raise Capacity
              requests only.
            </p>
            <Link to={back.to} className="req-view">Back to {back.label}</Link>
          </div>
        )}

        {(record.status !== 'ready' || found) && (
          <>
            <div className="rv-head">
              <span className="rv-head__kicker">Raise Capacity review</span>
              <h1 className="rv-head__title adm-mono">{requestId}</h1>
              {found?.request.details && (
                <p className="rv-head__summary">
                  {[found.request.details.courseId, found.request.details.courseName].filter(Boolean).join(' ')} ·
                  Section {found.request.details.sectionId} · {found.request.details.term}
                  {found.student?.name ? ` · ${found.student.name}` : ''}
                </p>
              )}
            </div>

            {record.status === 'loading' && (
              <div className="req-state" role="status">
                <p className="req-state__body">Loading request and student details…</p>
              </div>
            )}
            {record.status === 'error' && (
              <div className="req-state" role="alert">
                <h2 className="req-state__title">We couldn’t load the request and student details.</h2>
                <p className="req-state__body">Check your connection and try again.</p>
                <button type="button" className="req-button" onClick={record.retry}>
                  Try again
                </button>
              </div>
            )}

            {found && (
              <div className="rv-grid">
                <StudentPanel record={found} />
                <RequestPanel record={found} />
              </div>
            )}

            <section className="pcr-ai rca-ai" aria-labelledby="rca-ai-title">
              <div className="pcr-ai__head">
                <h2 id="rca-ai-title" className="pcr-ai__title">
                  AI Agent Evaluation
                </h2>
              </div>
              <div className="rca-ai__body">
                <PriorityPanel
                  status={priority.status}
                  data={priority.data}
                  error={priority.error}
                  running={priority.running}
                  notice={priority.notice}
                  onRetry={priority.retry}
                  onRerun={priority.rerun}
                  finalized={autoRun === false}
                />

                <EligibilityPanel
                  status={evaluation.status}
                  data={evaluation.data}
                  error={evaluation.error}
                  running={evaluation.running}
                  notice={evaluation.notice}
                  onRerun={evaluation.rerun}
                  onRetry={evaluation.retry}
                  finalized={autoRun === false}
                  courseNames={names}
                  onUseReason={decidable && decisionStep === 'form' ? applyReason : null}
                />
              </div>
            </section>

            {found && (
              <DecisionPanel
                key={found.request.id}
                record={found}
                choice={choice}
                onChoiceChange={setChoice}
                explanation={explanation}
                onExplanationChange={setExplanation}
                onStepChange={setDecisionStep}
                onChanged={record.refresh}
              />
            )}
          </>
        )}
      </div>
    </StudentLayout>
  )
}

export default AdminRaiseCapacityReview
