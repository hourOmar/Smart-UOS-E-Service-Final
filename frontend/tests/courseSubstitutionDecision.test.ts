// The Course Substitution decision rules and review record. Run: npm test
// (Node's built-in test runner; no browser or database).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  COURSE_SUBSTITUTION_DECISION_TYPES,
  UNKNOWN_DECISION_MESSAGE,
  courseSubstitutionDecisionErrorCode,
  courseSubstitutionDecisionErrorMessage,
  decisionExplanationError,
  differsFromRecommendation,
  evaluationWarning,
  explanationRequired,
  explanationToSend,
} from '../src/utils/courseSubstitutionDecision.ts'

test('Approve needs no explanation; Reject requires one (the database rule)', () => {
  // Approve without an explanation: no error, nothing sent.
  assert.equal(explanationRequired('approve'), false)
  assert.equal(decisionExplanationError('approve', '', true), null)
  assert.equal(explanationToSend('approve', ''), '')
  // A rejection explanation typed before switching to Approve is never sent with the approval.
  assert.equal(explanationToSend('approve', 'The proposed course does not match.'), '')
  // Reject without an explanation: blocked with the existing message.
  assert.equal(explanationRequired('reject'), true)
  assert.equal(decisionExplanationError('reject', '', true), 'Enter an explanation for the student.')
  assert.equal(decisionExplanationError('reject', '   ', true), 'Enter an explanation for the student.')
  assert.equal(decisionExplanationError('reject', '', false), null)
  // The 2,000-character limit is unchanged.
  assert.equal(decisionExplanationError('reject', 'x'.repeat(2000), true), null)
  assert.match(decisionExplanationError('reject', 'x'.repeat(2001), false) ?? '', /at most 2,000 characters/)
  // Reject with an explanation: allowed, sent trimmed.
  assert.equal(decisionExplanationError('reject', 'The outcomes differ.', true), null)
  assert.equal(explanationToSend('reject', '  The outcomes differ.  '), 'The outcomes differ.')
  // No choice yet: no explanation field and no explanation error.
  assert.equal(explanationRequired(null), false)
  assert.equal(decisionExplanationError(null, '', true), null)
  // Database refusals are still worded for staff.
  assert.equal(courseSubstitutionDecisionErrorMessage('explanation_required'), 'Enter an explanation for the student.')
  assert.equal(courseSubstitutionDecisionErrorMessage('not_staff'), 'Only staff members linked in Authorized_Staff can decide requests.')
})
import { buildCourseSubstitutionRecord, courseTitle, distinctDescription } from '../src/utils/courseSubstitutionRecord.ts'
import { courseSubstitutionReviewPath } from '../src/utils/adminPaths.ts'

test('the decision types match the database function', () => {
  assert.deepEqual(COURSE_SUBSTITUTION_DECISION_TYPES, {
    approve: 'Course Substitution Approved',
    reject: 'Course Substitution Rejected',
  })
})

test('every refusal of decide_course_substitution_request has a staff-facing message', () => {
  for (const code of ['not_staff', 'invalid_decision', 'explanation_required', 'explanation_too_long', 'request_not_found',
    'not_course_substitution', 'course_substitution_details_missing', 'already_decided']) {
    assert.equal(courseSubstitutionDecisionErrorCode({ message: code }), code)
    assert.notEqual(courseSubstitutionDecisionErrorMessage(code), UNKNOWN_DECISION_MESSAGE)
  }
})

test('session errors are signed_out; anything else is unknown and never shown raw', () => {
  assert.equal(courseSubstitutionDecisionErrorCode({ code: 'PGRST301', message: 'x' }), 'signed_out')
  assert.equal(courseSubstitutionDecisionErrorCode({ message: 'JWT expired' }), 'signed_out')
  assert.equal(courseSubstitutionDecisionErrorCode({ message: 'permission denied for function x' }), 'signed_out')
  assert.equal(courseSubstitutionDecisionErrorCode({ message: 'duplicate key value violates "Decision_pkey"' }), 'unknown')
  assert.equal(courseSubstitutionDecisionErrorCode(null), 'unknown')
  assert.equal(courseSubstitutionDecisionErrorMessage('unknown'), UNKNOWN_DECISION_MESSAGE)
  // Inherited object keys are not refusal codes.
  assert.equal(courseSubstitutionDecisionErrorCode({ message: 'toString' }), 'unknown')
})

test('a choice differs from ELIGIBLE / NOT_ELIGIBLE, and always from MANUAL_REVIEW', () => {
  assert.equal(differsFromRecommendation('approve', 'ELIGIBLE'), false)
  assert.equal(differsFromRecommendation('reject', 'ELIGIBLE'), true)
  assert.equal(differsFromRecommendation('reject', 'NOT_ELIGIBLE'), false)
  assert.equal(differsFromRecommendation('approve', 'NOT_ELIGIBLE'), true)
  assert.equal(differsFromRecommendation('approve', 'MANUAL_REVIEW'), true)
  assert.equal(differsFromRecommendation('reject', 'MANUAL_REVIEW'), true)
  assert.equal(differsFromRecommendation(null, 'ELIGIBLE'), false)
  assert.equal(differsFromRecommendation('approve', null), false)
})

test('the evaluation warning never blocks and is silent with a completed result or while loading', () => {
  const base = { loading: false, hasCompleted: true, latestFailed: false, running: false, unavailable: false }
  assert.equal(evaluationWarning(base), null)
  assert.equal(evaluationWarning({ ...base, loading: true, hasCompleted: false }), null)
  assert.match(evaluationWarning({ ...base, unavailable: true }) ?? '', /could not be loaded. You can still decide/)
  assert.match(evaluationWarning({ ...base, running: true }) ?? '', /advisory only/)
  assert.match(evaluationWarning({ ...base, hasCompleted: false, latestFailed: true }) ?? '', /failed/)
  assert.match(evaluationWarning({ ...base, hasCompleted: false }) ?? '', /no completed AI evaluation/)
})

test('the review record reads both courses, the reason and the latest decision', () => {
  const record = buildCourseSubstitutionRecord({
    request: { Request_ID: 'R1', Request_Type: 'Course Substitution', Current_Status: 'Completed', Request_Date: '2026-11-01',
      Submission_Time: '10:05:00', Description: ' Needs it to graduate ', Student_ID: 202312345 },
    details: { Original_Course_ID: 'CS401', Proposed_Course_ID: 'CS455', Reason: 'Needs it to graduate' },
    originalCourse: { Course_Name: 'Compilers', Credit_Hours: 3 },
    proposedCourse: null,
    student: { Student_ID: 202312345, Student_Name: 'A Student', Program_Name: 'Computer Science', Program: [{ College_Name: 'Computing' }] },
    decision: { Decision_ID: 7, Decision_Type: 'Course Substitution Approved', Decision_Comment: 'OK', Staff_ID: 3,
      Decision_Date: '2026-11-02 08:00:00', Authorized_Staff: { Staff_Name: 'Dr. X' } },
    history: { Final_Status: 'Completed', Staff_ID: 3, Completion_Date: '2026-11-02T08:00:00+00:00' },
  })
  assert.deepEqual(record.request.details, {
    original: { id: 'CS401', name: 'Compilers', creditHours: 3 },
    proposed: { id: 'CS455', name: null, creditHours: null },
    reason: 'Needs it to graduate',
  })
  assert.equal(courseTitle(record.request.details?.original), 'CS401 Compilers')
  assert.equal(courseTitle(record.request.details?.proposed), 'CS455')
  assert.equal(record.student?.college, 'Computing')
  assert.equal(record.decision?.choice, 'approve')
  assert.equal(record.decision?.date, '2026-11-02T08:00:00Z')
  assert.equal(record.history?.date, '2026-11-02T08:00:00+00:00')
  // The description only repeats the reason, so it is shown once.
  assert.equal(distinctDescription(record.request.details?.reason, record.request.summary), null)
})

test('missing details, student, decision and history are null, not errors', () => {
  const record = buildCourseSubstitutionRecord({
    request: { Request_ID: 'R2', Request_Type: 'Course Substitution', Current_Status: 'In Progress', Student_ID: 1 },
    details: null, originalCourse: null, proposedCourse: null, student: null, decision: null, history: null,
  })
  assert.equal(record.request.details, null)
  assert.equal(record.student, null)
  assert.equal(record.decision, null)
  assert.equal(record.history, null)
  assert.equal(courseTitle(null), null)
})

test('the review path encodes the request ID', () => {
  assert.equal(courseSubstitutionReviewPath('a/b'), '/admin/requests/course-substitution/a%2Fb')
})
