import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Coins, Layers, Download, AlertCircle, CheckCircle, Loader2, HelpCircle, Mail, Sparkles } from 'lucide-react'
import { api } from '../api.js'
import TemplatePickerModal from './TemplatePickerModal.jsx'

const BASE_INTERVAL = 3500
const BACKOFF_AFTER_MS = 5 * 60 * 1000
const MAX_INTERVAL = 30000

const CIRCUMFERENCE = 2 * Math.PI * 34 // r=34

function ScoreRing({ value, label, sub, color }) {
  const [displayed, setDisplayed] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => setDisplayed(value ?? 0), 120)
    return () => clearTimeout(t)
  }, [value])

  const pct = Math.min(Math.max(displayed, 0), 100)
  const offset = CIRCUMFERENCE * (1 - pct / 100)

  return (
    <div className="score-card">
      <div className="score-ring-wrap">
        <svg width="80" height="80" viewBox="0 0 80 80">
          <circle className="score-ring-bg" cx="40" cy="40" r="34" />
          <circle
            className="score-ring-fill"
            cx="40" cy="40" r="34"
            stroke={color || 'var(--accent)'}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="score-ring-text">
          <span className="score-value" style={{ fontSize: 16, color: color || 'var(--accent)' }}>
            {value != null ? `${value}%` : '—'}
          </span>
        </div>
      </div>
      <div className="score-label">{label}</div>
      {sub && <div className="score-sub">{sub}</div>}
    </div>
  )
}

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
    const saved = localStorage.getItem('cv_template')
    const savedColor = localStorage.getItem('cv_accent')
    if (saved) setTemplate(saved)
    if (savedColor) setAccentColor(savedColor)
  }, [token])

  useEffect(() => {
    if (!threadId) { setPolling(false); return }
    setPolling(true)
    startTimeRef.current = Date.now()
    intervalRef.current = BASE_INTERVAL

    const poll = async () => {
      const { data, ok } = await api.getStatus(token, threadId)
      if (!ok) return
      setSessionData(data)
      const terminal = ['complete', 'ineligible', 'error'].includes(data.status)
      if (terminal) { setPolling(false); clearTimeout(timerRef.current); return }
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
    if (jd.trim().length < 50) {
      setError('Please paste a complete job description (at least 50 characters).')
      return
    }
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
    const incomplete = gaps.some((_, i) => !gapAnswers[i] || gapAnswers[i].trim().length < 3)
    if (incomplete) {
      setError('Please answer all questions (at least 3 characters each).')
      return
    }
    setError('')
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

  // ── Complete ──────────────────────────────────────────────────────────────
  if (sessionData?.status === 'complete') {
    const elig = sessionData.eligibility_score ?? 0
    const ats  = sessionData.ats_score
    return (
      <div className="page">
        <div className="alert alert-success" style={{ marginBottom: 20 }}>
          <CheckCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
          Your optimized CV is ready — download it below.
        </div>

        <div className="score-grid" style={{ marginBottom: 20 }}>
          <ScoreRing value={elig} label="Fit Score" sub="Role eligibility" color="#059669" />
          <ScoreRing value={ats} label="ATS Score" sub="Keyword match" color="var(--accent)" />
        </div>

        {sessionData.pdf_url ? (
          <div className="card card-hover" style={{ marginBottom: 12 }}>
            <div className="card-title">Your CV</div>
            <a className="btn btn-primary" href={sessionData.pdf_url} target="_blank" rel="noreferrer">
              <Download size={15} />
              Download CV PDF
            </a>
          </div>
        ) : (
          <div className="alert alert-warning" style={{ marginBottom: 12 }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <strong>CV PDF unavailable.</strong> The PDF could not be generated this time.
              Please try again — if the problem persists, contact support.
            </div>
          </div>
        )}

        {sessionData.cover_letter_text && (
          <div className="card card-hover" style={{ marginBottom: 12 }}>
            <div className="card-title">Cover Letter</div>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14 }}>
              Draft generated. Edit it in the Cover Letter tab.
            </p>
            <div className="action-row">
              <button className="btn btn-secondary" onClick={() => openCoverLetter(sessionData)}>
                <Mail size={14} />
                Edit cover letter
              </button>
              {sessionData.cover_letter_pdf_url && (
                <a className="btn btn-secondary" href={sessionData.cover_letter_pdf_url} target="_blank" rel="noreferrer">
                  <Download size={14} />
                  Download PDF
                </a>
              )}
            </div>
          </div>
        )}

        <button className="btn btn-ghost" onClick={handleReset}>
          Generate another CV
        </button>
      </div>
    )
  }

  // ── Ineligible ───────────────────────────────────────────────────────────
  if (sessionData?.status === 'ineligible') {
    return (
      <div className="page">
        <div className="alert alert-error">
          <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            Your profile doesn't match this role well enough (fit score: {sessionData.eligibility_score ?? 0}/100).
            Try a different job description that better fits your experience.
          </div>
        </div>
        <button className="btn btn-secondary" onClick={handleReset}>Try another job</button>
      </div>
    )
  }

  // ── Error ────────────────────────────────────────────────────────────────
  if (sessionData?.status === 'error') {
    return (
      <div className="page">
        <div className="alert alert-error">
          <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
          Something went wrong during generation. Please try again.
        </div>
        <button className="btn btn-secondary" onClick={handleReset}>Try again</button>
      </div>
    )
  }

  // ── HITL questions ────────────────────────────────────────────────────────
  if (sessionData?.status === 'awaiting_hitl') {
    const gaps = sessionData.gaps || []
    return (
      <div className="page hitl-page">
        <div className="hitl-header">
          <div className="hitl-header-title">A few quick questions</div>
          <div className="hitl-header-sub">
            We noticed some gaps. Your answers help us tailor the CV accurately — takes about a minute.
          </div>
        </div>
        {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
        <form onSubmit={handleHitlSubmit}>
          {gaps.map((gap, i) => (
            <div className="field" key={i}>
              <div className="hitl-q-number">Question {i + 1} of {gaps.length}</div>
              <label style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', display: 'block', marginBottom: 6 }}>
                {gap}
              </label>
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
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button className="btn btn-primary" type="submit">
              <CheckCircle size={15} />
              Submit and continue
            </button>
            <button className="btn btn-ghost" type="button" onClick={handleReset}>Cancel</button>
          </div>
        </form>
      </div>
    )
  }

  // ── Cover letter options ──────────────────────────────────────────────────
  if (sessionData?.status === 'awaiting_cover_letter_options') {
    return (
      <div className="page">
        <div className="hitl-header" style={{ marginBottom: 22 }}>
          <div className="hitl-header-title">Customize your cover letter</div>
          <div className="hitl-header-sub">Your CV is ready. Choose how the cover letter should read.</div>
        </div>
        <form onSubmit={handleClOptions}>
          <div className="cl-options-grid">
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Tone</label>
              <select value={clTone} onChange={e => setClTone(e.target.value)}>
                <option value="formal">Formal — structured business letter</option>
                <option value="conversational">Conversational — modern, friendly</option>
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
          <div style={{ marginTop: 18 }}>
            <button className="btn btn-primary" type="submit">
              <Mail size={15} />
              Generate cover letter
            </button>
          </div>
        </form>
      </div>
    )
  }

  // ── Running / generating ──────────────────────────────────────────────────
  if (threadId && sessionData?.status === 'running') {
    return (
      <div className="page">
        <div className="loading-page">
          <div className="loading-spinner" />
          <div className="loading-title">Analyzing and tailoring your CV</div>
          <div className="loading-sub">Usually takes 1–2 minutes. The page updates automatically.</div>
          <div className="loading-steps">
            {[
              'Extracting job requirements',
              'Matching against your profile',
              'Scoring ATS keywords',
              'Rewriting and optimizing',
            ].map((step, i) => (
              <div key={i} className={`loading-step${i === 2 ? ' active' : ''}`}>
                <div className="loading-step-dot" />
                {step}
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // ── Default: generate form ────────────────────────────────────────────────
  return (
    <div className="page">
      <div className="hero-banner">
        <div className="hero-title">Generate your perfect CV</div>
        <div className="hero-sub">
          Paste a job description — we'll tailor your CV to match it and score it against ATS systems in under 2 minutes.
        </div>
        <div className="hero-chips">
          <span className="hero-chip"><CheckCircle size={11} /> ATS-optimized</span>
          <span className="hero-chip"><Layers size={11} /> 6 templates</span>
          <span className="hero-chip"><HelpCircle size={11} /> Smart gap analysis</span>
        </div>
      </div>

      {error && (
        <div className="alert alert-error">
          <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
          {error}
        </div>
      )}

      {balance !== null && (
        <div className="balance-bar">
          <div className="balance-chip">
            <Coins size={14} color="var(--warning)" />
            Balance: <strong>{balance} coins</strong>
          </div>
          <div className="balance-sep" />
          <div className="balance-chip">
            Cost: <strong>{costPerCv} coins per CV</strong>
          </div>
          <button className="btn btn-secondary" style={{ fontSize: 12.5, padding: '6px 14px' }} onClick={() => setShowTemplatePicker(true)}>
            <Layers size={13} />
            {template.charAt(0).toUpperCase() + template.slice(1)}
          </button>
        </div>
      )}

      <form onSubmit={handleGenerate}>
        <div className="field">
          <label>Job description</label>
          <textarea
            rows={12}
            placeholder="Paste the full job posting here — include responsibilities, requirements, and role details (minimum 100 words)..."
            value={jd}
            onChange={e => setJd(e.target.value)}
            required
          />
        </div>

        <div className="card" style={{ marginBottom: 18 }}>
          <label className="checkbox-label">
            <input type="checkbox" checked={coverLetter} onChange={e => setCoverLetter(e.target.checked)} />
            Also generate a tailored cover letter
          </label>

          {coverLetter && (
            <div className="cl-options-grid" style={{ marginTop: 14 }}>
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

        <button className="btn btn-primary btn-lg btn-full" disabled={starting} type="submit">
          {starting ? (
            <>
              <Loader2 size={16} style={{ animation: 'spin .7s linear infinite' }} />
              Starting...
            </>
          ) : (
            <>
              <Sparkles size={16} />
              Generate CV
            </>
          )}
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
