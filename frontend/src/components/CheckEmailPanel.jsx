import { useEffect, useState } from 'react'
import { supabase } from '../config.js'
import { Mail } from 'lucide-react'

export const RESEND_COOLDOWN_S = 60

export default function CheckEmailPanel({ email, onBack }) {
  const [left, setLeft] = useState(RESEND_COOLDOWN_S)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (left <= 0) return undefined
    const t = setTimeout(() => setLeft(l => l - 1), 1000)
    return () => clearTimeout(t)
  }, [left])

  async function resend() {
    setBusy(true)
    setNote('')
    const { error } = await supabase.auth.resend({
      type: 'signup',
      email,
      options: { emailRedirectTo: window.location.origin + '/auth/callback' },
    })
    setNote(error ? 'Could not resend right now. Please try again shortly.' : 'Confirmation email sent.')
    setLeft(RESEND_COOLDOWN_S)
    setBusy(false)
  }

  return (
    <div className="auth-check-email" style={{ textAlign: 'center' }}>
      <Mail size={28} />
      <h3>Check your email</h3>
      <p>We sent a confirmation link to <strong>{email}</strong>. Open it to activate your account, then sign in.</p>
      {note && <div className="alert alert-success">{note}</div>}
      <button className="btn btn-full" onClick={resend} disabled={busy || left > 0}>
        {left > 0 ? `Resend email (${left}s)` : 'Resend email'}
      </button>
      <button className="btn btn-full" type="button" onClick={onBack} style={{ marginTop: 8 }}>
        Back to sign in
      </button>
    </div>
  )
}
