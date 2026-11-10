import { useState } from 'react'

const TEMPLATES = [
  { id: 'classic',       name: 'Classic',       desc: 'Single-column, ATS-safe. Any profession.',             ats: true,  domains: 'All' },
  { id: 'modern',        name: 'Modern',        desc: 'Two-column sidebar. Tech, finance, corporate.',         ats: false, domains: 'Tech · Finance' },
  { id: 'compact',       name: 'Compact',       desc: 'Dense single-page. Recent graduates.',                  ats: true,  domains: 'All' },
  { id: 'academic',      name: 'Academic',      desc: 'Long-form with publications. Research and teaching.',   ats: false, domains: 'Education · Medical' },
  { id: 'trades',        name: 'Trades',        desc: 'Licenses and certs front-loaded. Skilled trades.',      ats: false, domains: 'Trades' },
  { id: 'creative',      name: 'Creative',      desc: 'Bold header, portfolio-style. Design and marketing.',   ats: false, domains: 'Creative' },
]

const SWATCHES = [
  '#4361ee', '#0ea5e9', '#10b981', '#8b5cf6',
  '#f59e0b', '#ef4444', '#ec4899', '#1e2139',
]

function TemplateMiniPreview({ id }) {
  if (id === 'modern') {
    return (
      <div style={{ display: 'flex', gap: 5, padding: 8, height: '100%' }}>
        <div style={{ width: '30%', background: '#e0e7ff', borderRadius: 3 }} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5, paddingTop: 4 }}>
          <div className="tpl-line header" style={{ background: '#4361ee', height: 8, width: '80%' }} />
          <div className="tpl-line" />
          <div className="tpl-line short" />
          <div className="tpl-line" />
          <div className="tpl-line short" />
        </div>
      </div>
    )
  }
  if (id === 'creative') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', padding: 8, height: '100%', gap: 5 }}>
        <div style={{ height: 22, background: '#4361ee', borderRadius: 3, marginBottom: 4 }} />
        <div className="tpl-line" />
        <div className="tpl-line short" />
        <div className="tpl-line" />
        <div className="tpl-line short" />
      </div>
    )
  }
  return (
    <div className="template-preview-lines" style={{ padding: '12px 0' }}>
      <div className="tpl-line header" />
      <div className="tpl-line" />
      <div className="tpl-line short" />
      <div className="tpl-line" />
      <div className="tpl-line" />
      <div className="tpl-line short" />
    </div>
  )
}

export default function TemplatePickerModal({ current, currentColor, onSelect, onClose }) {
  const [selected, setSelected] = useState(current)
  const [color, setColor] = useState(currentColor)
  const [customColor, setCustomColor] = useState(currentColor)

  function handleSwatch(c) {
    setColor(c)
    setCustomColor(c)
  }

  function handleCustomColor(e) {
    setCustomColor(e.target.value)
    if (/^#[0-9a-fA-F]{6}$/.test(e.target.value)) setColor(e.target.value)
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <span className="modal-title">Choose a template</span>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="template-grid">
          {TEMPLATES.map(t => (
            <div
              key={t.id}
              className={`template-card${selected === t.id ? ' selected' : ''}`}
              onClick={() => setSelected(t.id)}
            >
              {t.ats && <span className="ats-badge">ATS-safe</span>}
              <div className="template-thumb">
                <TemplateMiniPreview id={t.id} />
              </div>
              <div className="template-name">{t.name}</div>
              <div className="template-desc">{t.desc}</div>
              <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>{t.domains}</div>
            </div>
          ))}
        </div>

        <hr className="divider" />

        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, color: 'var(--text)' }}>Accent colour</div>
          <div className="swatch-row">
            {SWATCHES.map(s => (
              <div
                key={s}
                className={`swatch${color === s ? ' selected' : ''}`}
                style={{ background: s }}
                onClick={() => handleSwatch(s)}
                title={s}
              />
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input
              type="color"
              value={color}
              onChange={e => { setColor(e.target.value); setCustomColor(e.target.value) }}
              style={{ width: 32, height: 32, padding: 2, border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer' }}
            />
            <input
              type="text"
              value={customColor}
              onChange={handleCustomColor}
              maxLength={7}
              style={{ width: 90, padding: '5px 8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 13 }}
              placeholder="#4361ee"
            />
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>Custom hex</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => onSelect(selected, color)}>Apply</button>
        </div>
      </div>
    </div>
  )
}
