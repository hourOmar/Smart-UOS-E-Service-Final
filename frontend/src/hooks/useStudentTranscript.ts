import { useCallback, useEffect, useState } from 'react'
import { loadTranscript } from '../services/adminStudentProfile'
import type { TranscriptEntry } from '../utils/studentProfile'

type Status = 'loading' | 'ready' | 'error'

interface Loaded {
  forKey: string
  status: Exclude<Status, 'loading'>
  entries: TranscriptEntry[]
}

// One student's transcript, loaded and retried on its own so a failure never
// hides the rest of the page.
//
// `studentId` must come from a record already read from the database, never
// from a URL parameter or user input:
// - My Profile: the student's own record, as read by Auth UID
//   (services/studentProfile.ts);
// - Program Change review: the request's student, as read by staff.
// The database policies ("Students can view own academic records", "Staff can
// view academic records") limit the rows; the ID only narrows the query.
function useStudentTranscript(studentId: string | null) {
  const [attempt, setAttempt] = useState(0)
  const key = studentId ? `${studentId}#${attempt}` : ''
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  useEffect(() => {
    if (!studentId) return
    let cancelled = false
    loadTranscript(studentId)
      .then((entries) => {
        if (!cancelled) setLoaded({ forKey: key, status: 'ready', entries })
      })
      .catch(() => {
        if (!cancelled) setLoaded({ forKey: key, status: 'error', entries: [] })
      })
    return () => {
      cancelled = true
    }
  }, [studentId, key])

  const retry = useCallback(() => setAttempt((count) => count + 1), [])

  const current = loaded && loaded.forKey === key ? loaded : null
  return {
    status: (studentId ? (current?.status ?? 'loading') : 'error') as Status,
    entries: current?.entries ?? [],
    retry,
  }
}

export default useStudentTranscript
