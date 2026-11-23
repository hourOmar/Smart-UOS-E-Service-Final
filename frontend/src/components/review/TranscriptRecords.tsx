import { useState } from 'react'
import type { EvaluationRun, TranscriptRow } from '../../services/raiseCapacityReview'
import { NOT_RECORDED, courseLabel } from './format'

interface TranscriptRecordsProps {
  /** The evaluation whose prerequisite courses count as relevant, or null before any. */
  run: EvaluationRun | null
  requestedCourseId: string | null
  transcript: TranscriptRow[]
  courseNames: Map<string, string>
}

function relevantIds(run: EvaluationRun | null, requestedCourseId: string | null) {
  const ids = new Set<string>(requestedCourseId ? [requestedCourseId] : [])
  for (const group of run?.evidence?.checks.prerequisite.required_prerequisite_groups ?? []) {
    for (const id of group) ids.add(String(id))
  }
  return ids
}

// The student's transcript as recorded NOW (not the evaluation's snapshot): the requested
// course and its prerequisite courses, or the full transcript on request.
function TranscriptRecords({ run, requestedCourseId, transcript, courseNames }: TranscriptRecordsProps) {
  const [showAll, setShowAll] = useState(false)
  const hasEvidence = Boolean(run?.evidence?.checks)
  const relevant = relevantIds(run, requestedCourseId)
  const rows = showAll ? transcript : transcript.filter((row) => relevant.has(row.courseId))

  return (
    <details className="rca-transcript">
      <summary>
        Transcript records <span className="rv-live-tag">Current records</span>
      </summary>
      <div className="rca-transcript__body">
        <div className="rv-transcript__head">
          <p className="rv-muted">
            {showAll
              ? 'Every course on the student’s transcript, as recorded now.'
              : hasEvidence
                ? 'The requested course and its prerequisite courses, as recorded now (not the evaluation snapshot).'
                : 'The requested course, as recorded now. Prerequisite courses are added after the eligibility check.'}
          </p>
          {transcript.length > 0 && (
            <button type="button" className="rv-link-button" onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'Show relevant courses only' : `Show full transcript (${transcript.length})`}
            </button>
          )}
        </div>
        {rows.length > 0 ? (
          <div className="adm-table-wrap">
            <table className="adm-table rv-table">
              <thead>
                <tr>
                  <th scope="col">Course</th>
                  <th scope="col">Term</th>
                  <th scope="col">Section</th>
                  <th scope="col">Grade</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.courseId}-${row.term}-${row.sectionId}`}>
                    <td>{courseLabel(row.courseId, row.courseName ? new Map([[row.courseId, row.courseName]]) : courseNames)}</td>
                    <td className="adm-table__date">{row.term ?? NOT_RECORDED}</td>
                    <td>{row.sectionId ?? NOT_RECORDED}</td>
                    <td>{row.grade ?? 'No grade (in progress)'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rv-muted">
            {transcript.length === 0 ? 'The student has no transcript records.' : 'The student has no records for these courses.'}
          </p>
        )}
      </div>
    </details>
  )
}

export default TranscriptRecords
