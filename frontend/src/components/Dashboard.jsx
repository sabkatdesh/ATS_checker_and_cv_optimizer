import { useState } from 'react'
import { supabase } from '../config.js'
import HomeTab from './HomeTab.jsx'
import ProfileTab from './ProfileTab.jsx'
import HistoryTab from './HistoryTab.jsx'
import BillingTab from './BillingTab.jsx'
import CoverLetterTab from './CoverLetterTab.jsx'

const NAV = [
  { id: 'home',         label: 'Generate CV',   icon: '✦' },
  { id: 'profile',      label: 'My Profile',    icon: '◎' },
  { id: 'history',      label: 'Past CVs',      icon: '⊞' },
  { id: 'coverletter',  label: 'Cover Letter',  icon: '◈' },
  { id: 'billing',      label: 'Billing',       icon: '◉' },
]

export default function Dashboard({ session }) {
  const [tab, setTab] = useState('home')
  const [polling, setPolling] = useState(false)
  // Pass the selected session's cover letter to CoverLetterTab from HistoryTab
  const [clSession, setClSession] = useState(null)

  async function logout() {
    await supabase.auth.signOut()
  }

  function openCoverLetter(session) {
    setClSession(session)
    setTab('coverletter')
  }

  const token = session.access_token

  return (
    <div className="app-shell">
      {polling && (
        <div className="progress-bar-wrap">
          <div className="progress-bar-fill" />
        </div>
      )}

      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-name">CV Optimizer</div>
          <div className="sidebar-brand-sub">AI-powered tailoring</div>
        </div>

        <ul className="sidebar-nav">
          {NAV.map(n => (
            <li key={n.id}>
              <button
                className={tab === n.id ? 'active' : ''}
                onClick={() => setTab(n.id)}
              >
                <span style={{ fontSize: 11, opacity: .7 }}>{n.icon}</span>
                {n.label}
              </button>
            </li>
          ))}
        </ul>

        <div className="sidebar-footer">
          <div className="sidebar-user">{session.user.email}</div>
          <button className="btn btn-secondary btn-full" style={{ fontSize: 13 }} onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        {tab === 'home' && (
          <HomeTab
            token={token}
            setPolling={setPolling}
            openCoverLetter={openCoverLetter}
          />
        )}
        {tab === 'profile' && <ProfileTab token={token} />}
        {tab === 'history' && <HistoryTab token={token} openCoverLetter={openCoverLetter} />}
        {tab === 'coverletter' && <CoverLetterTab token={token} initialSession={clSession} />}
        {tab === 'billing' && <BillingTab token={token} />}
      </main>
    </div>
  )
}
