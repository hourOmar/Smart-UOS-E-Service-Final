import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import useStudentTranscript from '../../hooks/useStudentTranscript'
import { FOCUSABLE_SELECTOR, wrapFocusIndex } from '../../utils/dialogFocus'
import { termName } from '../../utils/studentProfile'
import { NOT_RECORDED } from '../review/format'
import TranscriptTerms from '../profile/TranscriptTerms'
import './TranscriptModal.css'

interface TranscriptModalProps {
  studentId: string
  studentName: string | null
  /** Program Change / Course Equivalency: the row is shown whenever this is passed (null shows "Not recorded"). */
  requestedProgram?: string | null
  /** Raise Capacity: the requested course; the row is shown whenever this is passed. */
  requestedCourse?: string | null
  /** The "records available in this system" notice; shown unless false (Raise Capacity hides it). */
  showNote?: boolean
  onClose: () => void
  /** The button that opened the modal; focus returns to it on close. */
  returnFocusRef: RefObject<HTMLElement | null>
}

// The student's transcript records over the review page, which stays mounted
// behind it. Render it only while open, so each opening reads current records.
// They are shown as stored: never totalled, reconciled with the recorded
// completed hours, or presented as complete or official.
function TranscriptModal({
  studentId,
  studentName,
  requestedProgram,
  requestedCourse,
  showNote = true,
  onClose,
  returnFocusRef,
}: TranscriptModalProps) {
  const { status, entries, retry } = useStudentTranscript(studentId)
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  // Separate from the key handler: this must run only on open and close, not
  // when the page behind re-renders (it polls while an evaluation runs).
  useEffect(() => {
    const opener = returnFocusRef.current
    // The page scrolls inside the student layout, not the body.
    const scroller = panelRef.current?.closest<HTMLElement>('.student') ?? null
    const previousScroller = scroller?.style.overflowY ?? ''
    const previousBody = document.body.style.overflow
    if (scroller) scroller.style.overflowY = 'hidden'
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    return () => {
      if (scroller) scroller.style.overflowY = previousScroller
      document.body.style.overflow = previousBody
      opener?.focus()
    }
  }, [returnFocusRef])

  // On the document, so the keys also work after focus has fallen to the body.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      const panel = panelRef.current
      if (event.key !== 'Tab' || !panel) return
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      const current = items.indexOf(document.activeElement as HTMLElement)
      const next = wrapFocusIndex(current, items.length, event.shiftKey)
      if (next === null) return
      event.preventDefault()
      items[next].focus()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const retryLoading = () => {
    // The retry button disappears while loading; keep focus inside the modal.
    closeRef.current?.focus()
    retry()
  }

  return (
    <div className="pcr-modal">
      <div className="pcr-modal__backdrop" aria-hidden="true" onClick={onClose} />
      <div
        ref={panelRef}
        className="pcr-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pcr-transcript-title"
        aria-describedby={showNote ? 'pcr-transcript-note' : undefined}
        tabIndex={-1}
      >
        <div className="pcr-modal__head">
          <h2 id="pcr-transcript-title" className="pcr-modal__title">
            Available transcript records
          </h2>
          <button ref={closeRef} type="button" className="pcr-modal__close" onClick={onClose}>
            Close
          </button>
        </div>

        {/* Focusable, so the records can be scrolled with the keyboard. */}
        <div className="pcr-modal__body" role="region" aria-label="Transcript details" tabIndex={0}>
          <dl className="pcr-modal__context">
            <div>
              <dt>Student name</dt>
              <dd>{studentName ?? NOT_RECORDED}</dd>
            </div>
            <div>
              <dt>Student ID</dt>
              <dd className="adm-mono">{studentId}</dd>
            </div>
            {requestedProgram !== undefined && (
              <div>
                <dt>Requested program</dt>
                <dd>{requestedProgram ?? NOT_RECORDED}</dd>
              </div>
            )}
            {requestedCourse !== undefined && (
              <div>
                <dt>Requested course</dt>
                <dd>{requestedCourse ?? NOT_RECORDED}</dd>
              </div>
            )}
          </dl>

          {showNote && (
            <p id="pcr-transcript-note" className="pcr-modal__note">
              These are the records available in this system. They may be incomplete and are not an official or
              verified transcript.
            </p>
          )}

          {status === 'loading' && (
            <p className="rv-muted" role="status">
              Loading transcript records…
            </p>
          )}
          {status === 'error' && (
            <div className="rv-alert" data-tone="failure" role="alert">
              <p className="rv-alert__title">The transcript records could not be loaded.</p>
              <p className="rv-alert__body">Check your connection and try again.</p>
              <button type="button" className="req-button" onClick={retryLoading}>
                Try again
              </button>
            </div>
          )}
          {status === 'ready' && (
            <TranscriptTerms
              entries={entries}
              emptyMessage="No transcript records are available in this system for this student."
              termTitle={termName}
              tableClassName="pcr-modal__table"
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default TranscriptModal
