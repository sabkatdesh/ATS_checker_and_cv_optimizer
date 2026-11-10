import { useState, useEffect, useRef } from 'react'
import { api } from '../api.js'
import TemplatePickerModal from './TemplatePickerModal.jsx'

const BASE_INTERVAL = 3500
const BACKOFF_AFTER_MS = 5 * 60 * 1000
const MAX_INTERVAL = 30000

export default function HomeTab({ token, setPolling, openCoverLetter }) {
  const [jd, setJd] = useState('')
  const [coverLetter, setCoverLetter] = useState(false)
  const [clTone, setClTone] = useState('formal')
  const [clLength, setClLength] = useState('standard')
  const [balance, setBalance] = useState(null)
  const [costPerCv, setCostPerCv] = useState(0)
  const [threadId, setThreadId] = useState(null)
  const [sessionData, setSessionData] = useState(null)
  const [gapAnswers, setGapAnswers] = useState([])
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)
  const [template, setTemplate] = useState('classic')
  const [accentColor, setAccentColor] = useState('#4361ee')

  const startTimeRef = useRef(null)
  const intervalRef = useRef(BASE_INTERVAL)
  const timerRef = useRef(null)

  useEffect(() => {
    api.getBalance(token).then(({ data }) => {
      setBalance(data.balance ?? 0)
      setCostPerCv(data.cost_per_cv ?? 0)
    })
    // Load saved template preference from localStorage
    const saved = localStorage.getItem('cv_template')
    const savedColor = localStorage.getItem('cv_accent')
    if (saved) setTemplate(saved)
    if (savedColor) setAccentColor(savedColor)
  }, [token])

  // ── Polling with exponential backoff ───────────────────────────────────────
  useEffect(() => {
    if (!threadId) { setPolling(false); return }
    setPolling(true)
    startTimeRef.current = Date.now()
    intervalRef.current = BASE_INTERVAL

    const poll = async () => {
      const { data, ok } = await api.getStatus(token, threadId)
      if (!ok) return
      setSessionData(data)

      const status = data.status
      const terminal = ['complete', 'ineligible', 'error'].includes(status)

      if (terminal) {
        setPolling(false)
        clearTimeout(timerRef.current)
        return
      }

      // Exponential backoff after BACKOFF_AFTER_MS
      const elapsed = Date.now() - startTimeRef.current
      if (elapsed > BACKOFF_AFTER_MS) {
        intervalRef.current = Math.min(intervalRef.current * 1.5, MAX_INTERVAL)
      }

      timerRef.current = setTimeout(poll, intervalRef.current)
    }

    poll()
    return () => { clearTimeout(timerRef.current); setPolling(false) }
  }, [threadId])

  async function handleGenerate(e) {
    e.preventDefault()
    if (jd.trim().length < 50) { setError('Please paste a complete job description (at least 50 characters).'); return }
    setError('')
    setStarting(true)
    setSessionData(null)

    const body = {
      job_description: jd,
      cover_letter: coverLetter,
      cover_letter_tone: coverLetter ? clTone : null,
      cover_letter_length: coverLetter ? clLength : null,
    }

    const { data, status } = await api.startSession(token, body)
    setStarting(false)

    if (status === 200) {
      setThreadId(data.thread_id)
    } else if (status === 400 && data.detail?.toLowerCase().includes('profile')) {
      setError('Please complete your profile first before generating a CV.')
    } else {
      setError(data.detail || 'Something went wrong. Please try again.')
    }
  }

  async function handleHitlSubmit(e) {
    e.preventDefault()
    const gaps = sessionData.gaps || []
    const qna = gaps.map((g, i) => `Q${i+1}: ${g}\nA${i+1}: ${gapAnswers[i] || ''}`).join('\n\n')
    const { ok } = await api.replyHitl(token, threadId, qna)
    if (ok) setSessionData(prev => ({ ...prev, status: 'running' }))
  }

  async function handleClOptions(e) {
    e.preventDefault()
    const { ok } = await api.submitCoverLetterOptions(token, threadId, clTone, clLength)
    if (ok) setSessionData(prev => ({ ...prev, status: 'running' }))
  }

  function handleReset() {
    clearTimeout(timerRef.current)
    setThreadId(null)
    setSessionData(null)
    setJd('')
    setGapAnswers([])
    setError('')
  }

  function handleTemplateSelect(tmpl, color) {
    setTemplate(tmpl)
    setAccentColor(color)
    localStorage.setItem('cv_template', tmpl)
    localStorage.setItem('cv_accent', color)
    setShowTemplatePicker(false)
  }

  // ── Results view ──────────────────────────────────────────────────────────
  if (sessionData?.status === 'complete') {
    const elig = sessionData.eligibility_score ?? 0
    const ats  = sessionData.ats_score
    return (
      <div className="page">
        <div className="alert alert-success">Your optimized CV is ready.</div>

        <div className="score-grid">
          <div className="score-cell">
            <div className="score-value">{elig}%</div>
            <div className="score-label">Fit score</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>Role eligibility</div>
          </div>
          <div className="score-cell">
            <div className="score-value">{ats != null ? `${ats}%` : '—'}</div>
            <div className="score-label">ATS score</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>Keyword match</div>
          </div>
        </div>

        {sessionData.pdf_url && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-title">Your CV</div>
            <a className="btn btn-primary" href={sessionData.pdf_url} target="_blank" rel="noreferrer">
              Download PDF
            </a>
          </div>
        )}

        {sessionData.cover_letter_text && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-title">Cover letter</div>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
              A draft has been generated. You can edit it in the Cover Letter tab.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary" onClick={() => openCoverLetter(sessionData)}>
                Edit cover letter
              </button>
              {sessionData.cover_letter_pdf_url && (
                <a className="btn btn-secondary" href={sessionData.cover_letter_pdf_url} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
              )}
            </div>
          </div>
        )}

        <button className="btn btn-secondary" onClick={handleReset}>Generate another CV</button>
      </div>
    )
  }

  if (sessionData?.status === 'ineligible') {
    return (
      <div className="page">
        <div className="alert alert-error">
          Your profile doesn't match this role well enough to generate a CV (score: {sessionData.eligibility_score ?? 0}/100).
          Try a different job description that better fits your experience.
        </div>
        <button className="btn btn-secondary" onClick={handleReset}>Try another job</button>
      </div>
    )
  }

  if (sessionData?.status === 'error') {
    return (
      <div className="page">
        <div className="alert alert-error">Something went wrong during generation. Please try again.</div>
        <button className="btn btn-secondary" onClick={handleReset}>Try again</button>
      </div>
    )
  }

  if (sessionData?.status === 'awaiting_hitl') {
    const gaps = sessionData.gaps || []
    return (
      <div className="page">
        <h2 className="page-title">A few questions</h2>
        <p className="page-sub">We noticed some gaps between your profile and this role. Your answers help us tailor the CV accurately.</p>
        <form onSubmit={handleHitlSubmit}>
          {gaps.map((gap, i) => (
            <div className="field" key={i}>
              <label>{gap}</label>
              <input
                type="text"
                placeholder="Your answer..."
                value={gapAnswers[i] || ''}
                onChange={e => {
                  const a = [...gapAnswers]; a[i] = e.target.value; setGapAnswers(a)
                }}
              />
            </div>
          ))}
          <button className="btn btn-primary" type="submit">Submit and continue</button>
        </form>
      </div>
    )
  }

  if (sessionData?.status === 'awaiting_cover_letter_options') {
    return (
      <div className="page">
        <h2 className="page-title">Cover letter options</h2>
        <p className="page-sub">Your CV is ready. Choose how you'd like the cover letter to read.</p>
        <form onSubmit={handleClOptions}>
          <div className="field">
            <label>Tone</label>
            <select value={clTone} onChange={e => setClTone(e.target.value)}>
              <option value="formal">Formal — structured business letter</option>
              <option value="conversational">Conversational — modern, friendly tone</option>
            </select>
          </div>
          <div className="field">
            <label>Length</label>
            <select value={clLength} onChange={e => setClLength(e.target.value)}>
              <option value="standard">Standard (~300 words)</option>
              <option value="short">Short (~150 words)</option>
            </select>
          </div>
          <button className="btn btn-primary" type="submit">Generate cover letter</button>
        </form>
      </div>
    )
  }

  if (threadId && sessionData?.status === 'running') {
    return (
      <div className="page">
        <h2 className="page-title">Analyzing your CV</h2>
        <p className="page-sub">This usually takes 1–2 minutes. The page will update when ready.</p>
        <div className="alert alert-info">
          Matching your profile against the job description, scoring ATS fit, and rewriting…
        </div>
      </div>
    )
  }

  // ── Default: form view ───────────────────────────────────────────────────
  return (
    <div className="page">
      <h2 className="page-title">Generate optimized CV</h2>
      <p className="page-sub">Paste a job description and we'll tailor your CV to match it.</p>

      {error && <div className="alert alert-error">{error}</div>}

      {balance !== null && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            Balance: <strong style={{ color: 'var(--text)' }}>{balance} coins</strong>
          </span>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>·</span>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            Cost: <strong style={{ color: 'var(--text)' }}>{costPerCv} coins</strong>
          </span>
          <span style={{ marginLeft: 'auto' }}>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: '5px 12px' }} onClick={() => setShowTemplatePicker(true)}>
              Template: {template}
            </button>
          </span>
        </div>
      )}

      <form onSubmit={handleGenerate}>
        <div className="field">
          <label>Job description</label>
          <textarea
            rows={12}
            placeholder="Paste the full job description here..."
            value={jd}
            onChange={e => setJd(e.target.value)}
            required
          />
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 14, fontWeight: 500 }}>
            <input type="checkbox" checked={coverLetter} onChange={e => setCoverLetter(e.target.checked)} />
            Also generate a cover letter
          </label>

          {coverLetter && (
            <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="field" style={{ marginBottom: 0 }}>
                <label>Tone</label>
                <select value={clTone} onChange={e => setClTone(e.target.value)}>
                  <option value="formal">Formal</option>
                  <option value="conversational">Conversational</option>
                </select>
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <label>Length</label>
                <select value={clLength} onChange={e => setClLength(e.target.value)}>
                  <option value="standard">Standard (~300 words)</option>
                  <option value="short">Short (~150 words)</option>
                </select>
              </div>
            </div>
          )}
        </div>

        <button className="btn btn-primary" disabled={starting} type="submit">
          {starting ? 'Starting...' : 'Generate CV'}
        </button>
      </form>

      {showTemplatePicker && (
        <TemplatePickerModal
          current={template}
          currentColor={accentColor}
          onSelect={handleTemplateSelect}
          onClose={() => setShowTemplatePicker(false)}
        />
      )}
    </div>
  )
}
