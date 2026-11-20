import { useState } from 'react'
import { supabase } from '../config.js'
import { motion } from 'framer-motion'
import { Zap, Mail, Lock, Loader2 } from 'lucide-react'
import CheckEmailPanel from './CheckEmailPanel.jsx'
import { useTurnstile } from './useTurnstile.js'

const callbackUrl = () => window.location.origin + '/auth/callback'
const GOOGLE_ENABLED = import.meta.env.VITE_AUTH_GOOGLE === '1'

export default function Auth() {
  const [tab, setTab] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingEmail, setPendingEmail] = useState(null)
  const captcha = useTurnstile(tab === 'signup' && !pendingEmail)

  async function handleGoogle() {
    setError('')
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: callbackUrl() },
    })
    if (error) setError('Could not start Google sign-in.')
  }

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error?.code === 'email_not_confirmed') setPendingEmail(email)
    else if (error) setError('Invalid email or password.')
    setLoading(false)
  }

  async function handleSignup(e) {
    e.preventDefault()
    setError('')
    setInfo('')
    if (password !== confirm) { setError('Passwords do not match.'); return }
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (captcha.enabled && !captcha.token) { setError('Please complete the captcha.'); return }
    setLoading(true)
    const options = { emailRedirectTo: callbackUrl() }
    if (captcha.enabled) options.captchaToken = captcha.token
    const { error } = await supabase.auth.signUp({ email, password, options })
    if (error) { setError('Could not create account. Email may already be registered.'); captcha.reset() }
    else setPendingEmail(email)
    setLoading(false)
  }

  function switchTab(t) { setTab(t); setError(''); setInfo(''); setPendingEmail(null) }

  return (
    <div className="auth-wrap">
      <div className="auth-bg-orb auth-bg-orb-1" />
      <div className="auth-bg-orb auth-bg-orb-2" />

      <motion.div
        className="auth-box"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0, transition: { duration: .35, ease: [.4, 0, .2, 1] } }}
      >
        <div className="auth-brand">
          <div className="auth-brand-logo">
            <Zap size={22} color="#fff" strokeWidth={2.5} />
          </div>
          <div className="auth-brand-name">CV Optimizer</div>
          <div className="auth-brand-sub">Tailor your CV for any role in minutes.</div>
        </div>

        {pendingEmail ? (
          <CheckEmailPanel email={pendingEmail} onBack={() => switchTab('login')} />
        ) : (<>
        <div className="auth-tabs">
          <button className={`auth-tab${tab === 'login' ? ' active' : ''}`} onClick={() => switchTab('login')}>
            Sign in
          </button>
          <button className={`auth-tab${tab === 'signup' ? ' active' : ''}`} onClick={() => switchTab('signup')}>
            Create account
          </button>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {info  && <div className="alert alert-success">{info}</div>}

        {tab === 'login' ? (
          <form onSubmit={handleLogin}>
            <div className="field">
              <label>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus placeholder="you@example.com" />
            </div>
            <div className="field">
              <label>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" />
            </div>
            <button className="btn btn-primary btn-full btn-lg" disabled={loading} style={{ marginTop: 4 }}>
              {loading ? <><Loader2 size={16} style={{ animation: 'spin .7s linear infinite' }} /> Signing in...</> : 'Sign in'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSignup}>
            <div className="field">
              <label>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus placeholder="you@example.com" />
            </div>
            <div className="field">
              <label>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="Minimum 8 characters" />
            </div>
            <div className="field">
              <label>Confirm password</label>
              <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required placeholder="••••••••" />
            </div>
            {captcha.enabled && <div ref={captcha.containerRef} style={{ margin: '8px 0' }} />}
            <button className="btn btn-primary btn-full btn-lg" disabled={loading} style={{ marginTop: 4 }}>
              {loading ? <><Loader2 size={16} style={{ animation: 'spin .7s linear infinite' }} /> Creating account...</> : 'Create account'}
            </button>
          </form>
        )}
        {GOOGLE_ENABLED && (
          <button type="button" className="btn btn-full" onClick={handleGoogle} style={{ marginTop: 12 }}>
            Continue with Google
          </button>
        )}
        </>)}
      </motion.div>
    </div>
  )
}
