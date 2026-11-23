import { useRef, useState } from 'react'
import { DOWNLOAD_MESSAGES, SyllabusDownloadError, downloadSyllabus } from '../../services/courseEquivalencyReview'
import type { SideUpload } from '../../hooks/useCourseEquivalencySyllabi'
import type { EvaluatedSyllabus, SyllabusSide } from '../../utils/courseEquivalencyEvaluation'
import {
  SIDE_HINTS,
  SIDE_TITLES,
  SYLLABUS_ACCEPT,
  fileTypeLabel,
  formatBytes,
  sourceLabel,
  type SyllabiState,
} from '../../utils/courseEquivalencySyllabi'
import { formatDateTime } from '../review/format'

const UPLOAD_LABELS: Record<SyllabusSide, string> = {
  old: 'Upload old syllabus',
  new: 'Upload new syllabus',
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M12 17v-6M9.5 13.5 12 11l2.5 2.5" />
    </svg>
  )
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  )
}

interface SyllabusPanelProps {
  requestId: string
  side: SyllabusSide
  status: 'loading' | 'ready' | 'error'
  data: SyllabiState | null
  error: string | null
  upload: SideUpload
  onUpload: (side: SyllabusSide, file: File) => void
  onReload: () => void
  /** The version the current evaluation used, to mark a replaced (outdated) file. */
  evaluated: EvaluatedSyllabus | null
}

// One side of the request's syllabi (Phase 3B): the current file with its details,
// authorized staff download (private bucket, staff session), and upload / replacement with
// progress and validation errors. Only the current syllabus exists: a replaced file is
// deleted by the backend once its replacement is saved.
function SyllabusPanel({ requestId, side, status, data, error, upload, onUpload, onReload, evaluated }: SyllabusPanelProps) {
  const input = useRef<HTMLInputElement>(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const sideState = data?.sides[side] ?? null
  const current = sideState?.current ?? null
  const canUpload = Boolean(data?.can_upload) && !upload.busy
  const titleId = `cer-syllabus-${side}-title`

  const download = async () => {
    if (!current) return
    setDownloading(true)
    setDownloadError(null)
    try {
      await downloadSyllabus(requestId, current)
    } catch (e) {
      setDownloadError(e instanceof SyllabusDownloadError ? e.message : DOWNLOAD_MESSAGES.unavailable)
    } finally {
      setDownloading(false)
    }
  }

  const chosen = (files: FileList | null) => {
    const file = files?.[0]
    if (input.current) input.current.value = ''
    if (file) onUpload(side, file)
  }

  return (
    <section className="req-panel rv-panel cer-syllabus" aria-labelledby={titleId} aria-busy={upload.busy}>
      <h2 id={titleId} className="req-panel__title">
        {SIDE_TITLES[side]}
      </h2>
      <div className="req-panel__body">
        <p className="rv-muted cer-syllabus__hint">{SIDE_HINTS[side]}</p>
        {status === 'loading' && <p className="rv-muted" role="status">Loading the syllabus…</p>}
        {status === 'error' && !data && (
          <div className="rv-notice" role="alert">
            {error}{' '}
            <button type="button" className="pcr-rerun" onClick={onReload}>
              Try again
            </button>
          </div>
        )}
        {data && (
          <input
            ref={input}
            id={`cer-upload-${side}`}
            type="file"
            accept={SYLLABUS_ACCEPT}
            className="student-visually-hidden"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => chosen(event.target.files)}
            disabled={!canUpload}
          />
        )}

        {/* No file yet: the upload area (button only; no drag-and-drop). */}
        {data && !current && (
          <div className="cer-dropzone" data-disabled={!data.can_upload || undefined}>
            <span className="cer-dropzone__icon">
              <UploadIcon />
            </span>
            <span className="cer-dropzone__label">{UPLOAD_LABELS[side]}</span>
            <span className="cer-dropzone__rules">PDF or DOCX, maximum 10 MB</span>
            <span className="cer-dropzone__missing" role="status">
              No syllabus uploaded yet. The eligibility check needs both syllabi.
            </span>
            <button
              type="button"
              className="pcr-primary cer-dropzone__button"
              onClick={() => input.current?.click()}
              disabled={!canUpload}
              title={!data.can_upload ? 'Syllabi can be uploaded only while the request is In Progress.' : undefined}
            >
              {upload.busy ? 'Uploading…' : 'Choose file'}
              <span className="student-visually-hidden"> for the {SIDE_TITLES[side].toLowerCase()}</span>
            </button>
          </div>
        )}

        {/* A current file: centered like the upload area, with its details and actions. */}
        {current && (
          <div className="cer-file">
            <span className="cer-file__icon">
              <FileIcon />
            </span>
            <span className="cer-file__status">
              <span aria-hidden="true">✓</span> Uploaded
            </span>
            <span className="cer-file__name" title={current.file_name}>
              {current.file_name}
            </span>
            <span className="cer-file__meta">
              {[fileTypeLabel(current.mime_type), formatBytes(current.size_bytes)].filter(Boolean).join(' · ')}
            </span>
            <span className="cer-file__by">
              {[formatDateTime(current.uploaded_at), sourceLabel(current)].filter(Boolean).join(' · ')}
            </span>
            {evaluated && evaluated.syllabus_id !== current.syllabus_id && (
              <span className="cer-syllabus__stale" role="note">
                Replaced after the current evaluation (it used “{evaluated.file_name}”).
              </span>
            )}
            <div className="cer-file__actions">
              <button type="button" className="pcr-rerun" onClick={() => void download()} disabled={downloading}>
                {downloading ? 'Downloading…' : 'Download'}
                <span className="student-visually-hidden"> {SIDE_TITLES[side]}</span>
              </button>
              {data && (
                <button
                  type="button"
                  className="pcr-rerun"
                  onClick={() => input.current?.click()}
                  disabled={!canUpload}
                  aria-describedby={`cer-replace-rules-${side}`}
                  title={
                    !data.can_upload
                      ? 'Syllabi can be uploaded only while the request is In Progress.'
                      : 'PDF or DOCX, maximum 10 MB'
                  }
                >
                  {upload.busy ? 'Uploading…' : 'Replace'}
                  <span className="student-visually-hidden"> {SIDE_TITLES[side]}</span>
                </button>
              )}
            </div>
            <span id={`cer-replace-rules-${side}`} className="student-visually-hidden">
              Replacement file: PDF or DOCX, maximum 10 MB.
            </span>
          </div>
        )}
        {data && !data.can_upload && (
          <span className="rv-muted cer-upload__rules">Uploads are closed: the request is no longer In Progress.</span>
        )}
        {downloadError && (
          <p className="rv-notice" role="alert">
            {downloadError}
          </p>
        )}
        {upload.progress !== null && (
          <div className="cer-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100}
               aria-valuenow={Math.round(upload.progress * 100)} aria-label={`Uploading the ${SIDE_TITLES[side].toLowerCase()}`}>
            <span className="cer-progress__bar" style={{ width: `${Math.round(upload.progress * 100)}%` }} />
          </div>
        )}
        {upload.error && (
          <p className="rv-notice" role="alert">
            {upload.error}
          </p>
        )}
        {upload.message && (
          <p className="cer-upload__done" role="status">
            {upload.message}
          </p>
        )}
      </div>
    </section>
  )
}

export default SyllabusPanel
