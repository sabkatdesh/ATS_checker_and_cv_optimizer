import { useState, useEffect } from 'react'
import { api } from '../api.js'

const TIERS = [
  { name: 'Starter',  coins: 50,  cvs: '~5 CVs',  price: '৳ 99',  desc: '' },
  { name: 'Popular',  coins: 150, cvs: '~15 CVs', price: '৳ 249', desc: 'Best value', featured: true },
  { name: 'Pro',      coins: 500, cvs: '~50 CVs', price: '৳ 699', desc: '' },
]

export default function BillingTab({ token }) {
  const [balance, setBalance] = useState(null)
  const [costPerCv, setCostPerCv] = useState(0)
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getBalance(token),
      api.getBillingHistory(token),
    ]).then(([balRes, histRes]) => {
      setBalance(balRes.data.balance ?? 0)
      setCostPerCv(balRes.data.cost_per_cv ?? 0)
      setTransactions(histRes.data.transactions || [])
      setLoading(false)
    })
  }, [token])

  if (loading) return <div className="page" style={{ color: 'var(--muted)' }}>Loading…</div>

  return (
    <div className="page">
      <h2 className="page-title">Billing</h2>
      <p className="page-sub">Coins are used each time you generate a CV.</p>

      {/* ── Balance ────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 28 }}>
        <div className="score-cell" style={{ flex: 'none', minWidth: 140 }}>
          <div className="score-value">{balance}</div>
          <div className="score-label">Your balance</div>
        </div>
        <div className="score-cell" style={{ flex: 'none', minWidth: 140 }}>
          <div className="score-value">{costPerCv}</div>
          <div className="score-label">Cost per CV</div>
        </div>
      </div>

      {/* ── Tiers ──────────────────────────────────────────────────────────── */}
      <div className="section-title">Buy coins</div>
      <div className="tier-grid">
        {TIERS.map(t => (
          <div key={t.name} className={`tier-card${t.featured ? ' featured' : ''}`}>
            <div className="tier-name">{t.name}{t.desc ? ` · ${t.desc}` : ''}</div>
            <div className="tier-price">{t.price}</div>
            <div className="tier-coins">{t.coins} coins &mdash; {t.cvs}</div>
            <button className="btn btn-secondary btn-full" disabled style={{ fontSize: 13 }}>
              Coming soon
            </button>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 28 }}>
        bKash and Nagad payments coming soon. Contact us to top up manually in the meantime.
      </p>

      {/* ── Transactions ───────────────────────────────────────────────────── */}
      <div className="section-title">Transaction history</div>
      {transactions.length === 0 ? (
        <div className="empty-state" style={{ padding: '24px 0' }}>
          <p>No transactions yet.</p>
        </div>
      ) : (
        <div className="card" style={{ padding: '4px 20px' }}>
          {transactions.map((t, i) => {
            const amount = t.amount ?? 0
            const pos = amount > 0
            return (
              <div key={i} className="txn-row">
                <span style={{ flex: 1, fontSize: 14 }}>{t.description || 'Transaction'}</span>
                <span style={{ fontSize: 12, color: 'var(--muted)', marginRight: 16 }}>
                  {(t.created_at || '').slice(0, 10)}
                </span>
                <span className={pos ? 'txn-amount-pos' : 'txn-amount-neg'}>
                  {pos ? '+' : ''}{amount}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
