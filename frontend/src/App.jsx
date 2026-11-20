import { useState, useEffect } from 'react'
import { supabase } from './config.js'
import Auth from './components/Auth.jsx'
import Dashboard from './components/Dashboard.jsx'
import { claimBonus } from './lib/bonus.js'

export default function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [bonusStatus, setBonusStatus] = useState(null)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })

    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!session) return
    claimBonus(session).then((status) => status && setBonusStatus(status))
  }, [session?.user?.id, session?.user?.email_confirmed_at])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div style={{ color: 'var(--muted)', fontSize: 14 }}>Loading...</div>
      </div>
    )
  }

  if (!session) return <Auth />
  return (
    <>
      {bonusStatus === 'pending_review' && (
        <div role="status" style={{ padding: '8px 16px', fontSize: 13, textAlign: 'center' }}>
          Bonus pending review
        </div>
      )}
      <Dashboard session={session} />
    </>
  )
}
