import { useState } from 'react'
import { supabase } from '../config.js'
import { motion } from 'framer-motion'
import { Zap, Mail, Lock, Loader2 } from 'lucide-react'

export default function Auth() {
  const [tab, setTab] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) setError('Invalid email or password.')
    setLoading(false)
  }

  async function handleSignup(e) {
    e.preventDefault()
    setError('')
    setInfo('')
    if (password !== confirm) { setError('Passwords do not match.'); return }
    if (password.length < 6) { setError('Password must be at least 6 characters.'); return }
    setLoading(true)
    const { error } = await supabase.auth.signUp({ email, password })
    if (error) setError('Could not create account. Email may already be registered.')
    else setInfo('Account created! Check your email to confirm, then sign in.')
    setLoading(false)
  }

  function switchTab(t) { setTab(t); setError(''); setInfo('') }

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
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="Minimum 6 characters" />
            </div>
            <div className="field">
              <label>Confirm password</label>
              <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required placeholder="••••••••" />
            </div>
            <button className="btn btn-primary btn-full btn-lg" disabled={loading} style={{ marginTop: 4 }}>
              {loading ? <><Loader2 size={16} style={{ animation: 'spin .7s linear infinite' }} /> Creating account...</> : 'Create account'}
            </button>
          </form>
        )}
      </motion.div>
    </div>
  )
}
