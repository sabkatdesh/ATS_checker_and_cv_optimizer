import { useEffect, useState } from 'react'
import { supabase, authCallbackUrl } from '../config.js'
import CaptchaBox from './CaptchaBox.jsx'
import { useTurnstile } from './useTurnstile.js'
import { Mail } from 'lucide-react'

export const RESEND_COOLDOWN_S = 60

export default function CheckEmailPanel({ email, onBack }) {
  const [left, setLeft] = useState(RESEND_COOLDOWN_S)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [noteIsError, setNoteIsError] = useState(false)
  const captcha = useTurnstile(true)

  useEffect(() => {
    if (left <= 0) return undefined
    const t = setTimeout(() => setLeft(l => l - 1), 1000)
    return () => clearTimeout(t)
  }, [left])

  async function resend() {
    setBusy(true)
    setNote('')
    const options = { emailRedirectTo: authCallbackUrl() }
    if (captcha.enabled) options.captchaToken = captcha.token
    const { error } = await supabase.auth.resend({ type: 'signup', email, options })
    const limited = error && (error.status === 429 || error.code === 'over_email_send_rate_limit')
    setNoteIsError(Boolean(error))
    setNote(!error ? 'Confirmation email sent.'
      : limited ? 'Too many emails requested. Please wait a few minutes and try again.'
      : 'Could not resend right now. Please try again shortly.')
    captcha.reset()
    setLeft(RESEND_COOLDOWN_S)
    setBusy(false)
  }

  const needsCaptcha = captcha.enabled && !captcha.token

  return (
    <div className="auth-check-email" style={{ textAlign: 'center' }}>
      <Mail size={28} />
      <h3>Check your email</h3>
      <p>We sent a confirmation link to <strong>{email}</strong>. Open it to activate your account, then sign in.</p>
      {note && <div className={`alert ${noteIsError ? 'alert-error' : 'alert-success'}`}>{note}</div>}
      <CaptchaBox captcha={captcha} />
      <button className="btn btn-full" onClick={resend} disabled={busy || left > 0 || needsCaptcha}>
        {left > 0 ? `Resend email (${left}s)` : 'Resend email'}
      </button>
      <button className="btn btn-full" type="button" onClick={onBack} style={{ marginTop: 8 }}>
        Back to sign in
      </button>
    </div>
  )
}
