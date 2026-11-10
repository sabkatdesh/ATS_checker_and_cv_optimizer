import { useState } from 'react'
import { supabase } from '../config.js'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, User, Clock, FileText, CreditCard, LogOut, Zap } from 'lucide-react'
import HomeTab from './HomeTab.jsx'
import ProfileTab from './ProfileTab.jsx'
import HistoryTab from './HistoryTab.jsx'
import BillingTab from './BillingTab.jsx'
import CoverLetterTab from './CoverLetterTab.jsx'

const NAV = [
  { id: 'home',        label: 'Generate CV',  Icon: Sparkles },
  { id: 'profile',     label: 'My Profile',   Icon: User },
  { id: 'history',     label: 'Past CVs',     Icon: Clock },
  { id: 'coverletter', label: 'Cover Letter', Icon: FileText },
  { id: 'billing',     label: 'Billing',      Icon: CreditCard },
]

const tabVariants = {
  initial:  { opacity: 0, y: 10 },
  animate:  { opacity: 1, y: 0, transition: { duration: .22, ease: [.4, 0, .2, 1] } },
  exit:     { opacity: 0, y: -6, transition: { duration: .15 } },
}

export default function Dashboard({ session }) {
  const [tab, setTab] = useState('home')
  const [polling, setPolling] = useState(false)
  const [clSession, setClSession] = useState(null)

  async function logout() {
    await supabase.auth.signOut()
  }

  function openCoverLetter(s) {
    setClSession(s)
    setTab('coverletter')
  }

  const token = session.access_token
  const email = session.user.email || ''
  const initials = email.slice(0, 2).toUpperCase()

  return (
    <div className="app-shell">
      {polling && (
        <div className="progress-bar-wrap">
          <div className="progress-bar-fill" />
        </div>
      )}

      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-dot">
            <Zap size={16} strokeWidth={2.5} />
          </div>
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-name">CV Optimizer</div>
            <div className="sidebar-brand-sub">AI-powered</div>
          </div>
        </div>

        <ul className="sidebar-nav">
          {NAV.map(({ id, label, Icon }) => (
            <li key={id}>
              <button
                className={`nav-btn${tab === id ? ' active' : ''}`}
                onClick={() => setTab(id)}
              >
                {tab === id && (
                  <motion.span
                    className="nav-active-bar"
                    layoutId="nav-indicator"
                    transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                  />
                )}
                <span className="nav-icon">
                  <Icon size={16} strokeWidth={2} />
                </span>
                {label}
              </button>
            </li>
          ))}
        </ul>

        <div className="sidebar-footer">
          <div className="sidebar-user-row">
            <div className="sidebar-avatar">{initials}</div>
            <div className="sidebar-user-email" title={email}>{email}</div>
          </div>
          <button className="btn-signout" onClick={logout}>
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            variants={tabVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            {tab === 'home' && (
              <HomeTab token={token} setPolling={setPolling} openCoverLetter={openCoverLetter} />
            )}
            {tab === 'profile' && <ProfileTab token={token} />}
            {tab === 'history' && <HistoryTab token={token} openCoverLetter={openCoverLetter} />}
            {tab === 'coverletter' && <CoverLetterTab token={token} initialSession={clSession} />}
            {tab === 'billing' && <BillingTab token={token} />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
