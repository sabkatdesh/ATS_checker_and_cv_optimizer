import { useState, useEffect } from 'react'
import { api } from '../api.js'

const STATUS_BADGE = {
  complete:                   { cls: 'badge-complete',  label: 'Complete' },
  running:                    { cls: 'badge-running',   label: 'Running' },
  awaiting_hitl:              { cls: 'badge-waiting',   label: 'Awaiting input' },
  awaiting_cover_letter_options: { cls: 'badge-waiting', label: 'Awaiting CL options' },
  ineligible:                 { cls: 'badge-ineligible',label: 'Not eligible' },
  error:                      { cls: 'badge-error',     label: 'Error' },
}

function SessionDetail({ session, onOpenCoverLetter }) {
  const [open, setOpen] = useState(false)

  const b = STATUS_BADGE[session.status] || { cls: 'badge-running', label: session.status }
  const date = session.created_at ? session.created_at.slice(0, 10) : '—'
  const jdSnippet = (session.job_description || '').slice(0, 80)

  return (
    <div style={{ marginBottom: 8 }}>
      <div className="session-row" onClick={() => setOpen(o => !o)}>
        <div className="session-row-main">
          <div className="session-date">{date}</div>
          <div className="session-snippet">{jdSnippet || 'CV generation'}{jdSnippet.length === 80 ? '…' : ''}</div>
        </div>
        <span className={`badge ${b.cls}`}>{b.label}</span>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="card" style={{ borderRadius: '0 0 8px 8px', borderTop: 'none', marginBottom: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 2 }}>Eligibility score</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--accent)' }}>
                {session.eligibility_score != null ? session.eligibility_score : '—'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 2 }}>ATS score</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--accent)' }}>
                {session.ats_score != null ? `${session.ats_score}%` : '—'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 2 }}>Template</div>
              <div style={{ fontSize: 14, fontWeight: 500 }}>
                {session.template_id || 'classic'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {session.pdf_url && (
              <a className="btn btn-primary" href={session.pdf_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                Download CV
              </a>
            )}
            {session.cover_letter_pdf_url && (
              <a className="btn btn-secondary" href={session.cover_letter_pdf_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                Download cover letter
              </a>
            )}
            {session.cover_letter_text && (
              <button className="btn btn-secondary" style={{ fontSize: 13 }} onClick={() => onOpenCoverLetter(session)}>
                Edit cover letter
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function HistoryTab({ token, openCoverLetter }) {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getSessions(token).then(({ data }) => {
      setSessions(data.sessions || [])
      setLoading(false)
    })
  }, [token])

  if (loading) return <div className="page" style={{ color: 'var(--muted)' }}>Loading…</div>

  return (
    <div className="page">
      <h2 className="page-title">Past CVs</h2>
      <p className="page-sub">Click a row to see scores, download your CV, or edit the cover letter.</p>

      {sessions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">⊞</div>
          <p>No CVs generated yet. Head to Generate CV to get started.</p>
        </div>
      ) : (
        sessions.map(s => (
          <SessionDetail
            key={s.thread_id || s.id}
            session={s}
            onOpenCoverLetter={openCoverLetter}
          />
        ))
      )}
    </div>
  )
}
