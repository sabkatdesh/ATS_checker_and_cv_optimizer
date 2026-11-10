import { useState, useEffect } from 'react'
import { api } from '../api.js'

export default function CoverLetterTab({ token, initialSession }) {
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState(null)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getSessions(token).then(({ data }) => {
      const withCL = (data.sessions || []).filter(s => s.cover_letter_text)
      setSessions(withCL)
      setLoading(false)
      // If navigated here from another tab with a specific session
      if (initialSession) {
        const match = withCL.find(s => (s.thread_id || s.id) === (initialSession.thread_id || initialSession.id))
        if (match) {
          setSelected(match)
          setText(match.cover_letter_text || '')
        } else {
          // Session passed directly (e.g., just generated)
          setSelected(initialSession)
          setText(initialSession.cover_letter_text || '')
        }
      } else if (withCL.length > 0) {
        setSelected(withCL[0])
        setText(withCL[0].cover_letter_text || '')
      }
    })
  }, [token])

  function selectSession(s) {
    setSelected(s)
    setText(s.cover_letter_text || '')
    setMsg('')
  }

  async function handleSave() {
    if (!selected) return
    setSaving(true)
    setMsg('')
    const threadId = selected.thread_id || selected.id
    const { ok } = await api.saveCoverLetter(token, threadId, text)
    setSaving(false)
    if (ok) {
      setMsg('Saved.')
      setSessions(prev => prev.map(s =>
        (s.thread_id || s.id) === threadId ? { ...s, cover_letter_text: text } : s
      ))
    } else {
      setMsg('Could not save.')
    }
  }

  if (loading) return <div className="page" style={{ color: 'var(--muted)' }}>Loading…</div>

  if (sessions.length === 0 && !initialSession) {
    return (
      <div className="page">
        <h2 className="page-title">Cover letter</h2>
        <div className="empty-state">
          <div className="empty-state-icon">◈</div>
          <p>No cover letters yet. Check the "Also generate a cover letter" option when generating a CV.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <h2 className="page-title">Cover letter</h2>
      <p className="page-sub">Edit the generated draft below, then download the final PDF.</p>

      {sessions.length > 1 && (
        <div className="field" style={{ marginBottom: 20 }}>
          <label>Select a session</label>
          <select
            value={selected ? (selected.thread_id || selected.id) : ''}
            onChange={e => {
              const s = sessions.find(x => (x.thread_id || x.id) === e.target.value)
              if (s) selectSession(s)
            }}
          >
            {sessions.map(s => (
              <option key={s.thread_id || s.id} value={s.thread_id || s.id}>
                {s.created_at ? s.created_at.slice(0, 10) : 'Session'} — {(s.job_description || '').slice(0, 50)}
              </option>
            ))}
          </select>
        </div>
      )}

      {selected && (
        <>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
            {selected.cover_letter_pdf_url && (
              <a className="btn btn-secondary" href={selected.cover_letter_pdf_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                Download current PDF
              </a>
            )}
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>Edit the text below and save to update your draft.</span>
          </div>

          <textarea
            className="cl-editor"
            value={text}
            onChange={e => setText(e.target.value)}
            spellCheck
          />

          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 12 }}>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save draft'}
            </button>
            {msg && <span style={{ fontSize: 13, color: msg === 'Saved.' ? 'var(--success)' : 'var(--error)' }}>{msg}</span>}
          </div>

          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 10 }}>
            After saving, re-download the PDF from Past CVs to get the latest version.
          </p>
        </>
      )}
    </div>
  )
}
