import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Check } from 'lucide-react'

const TEMPLATES = [
  { id: 'classic',  name: 'Classic',  desc: 'Single-column, ATS-safe.',             ats: true,  domains: 'All professions' },
  { id: 'modern',   name: 'Modern',   desc: 'Two-column sidebar layout.',            ats: false, domains: 'Tech · Finance' },
  { id: 'compact',  name: 'Compact',  desc: 'Dense single-page for graduates.',      ats: true,  domains: 'All professions' },
  { id: 'academic', name: 'Academic', desc: 'Long-form with publications section.',  ats: false, domains: 'Education · Medical' },
  { id: 'trades',   name: 'Trades',   desc: 'Licences front-loaded.',                ats: false, domains: 'Trades' },
  { id: 'creative', name: 'Creative', desc: 'Bold header, portfolio-style.',         ats: false, domains: 'Design · Marketing' },
]

const SWATCHES = [
  '#4361ee', '#0ea5e9', '#10b981', '#8b5cf6',
  '#f59e0b', '#ef4444', '#ec4899', '#1e2139',
]

// Rich mini CV previews — each template renders a distinct layout
// accent is passed as a prop and used directly in inline styles
function TemplateMiniCV({ id, accent }) {
  const line = (w, h = 3, bg = '#e5e7eb', style = {}) => (
    <div style={{ height: h, width: w, background: bg, borderRadius: 2, flexShrink: 0, ...style }} />
  )

  if (id === 'modern') {
    return (
      <div style={{ display: 'flex', height: '100%', fontSize: 0 }}>
        {/* sidebar */}
        <div style={{ width: '32%', background: accent, opacity: .15, display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 5px' }}>
          <div style={{ width: 24, height: 24, borderRadius: '50%', background: accent, opacity: .6, margin: '0 auto 4px' }} />
          {[80, 70, 90, 60, 75].map((w, i) => (
            <div key={i} style={{ height: 3, width: `${w}%`, background: '#fff', borderRadius: 2, opacity: .5 }} />
          ))}
        </div>
        {/* main */}
        <div style={{ flex: 1, padding: '8px 7px', display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ height: 7, width: '75%', background: accent, borderRadius: 2 }} />
          <div style={{ height: 3.5, width: '50%', background: '#cbd5e1', borderRadius: 2 }} />
          <div style={{ height: 1, background: accent, opacity: .3, margin: '3px 0' }} />
          {[95, 80, 65, 90, 70, 55].map((w, i) => (
            <div key={i} style={{ height: 3, width: `${w}%`, background: '#e5e7eb', borderRadius: 2 }} />
          ))}
        </div>
      </div>
    )
  }

  if (id === 'creative') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', fontSize: 0 }}>
        {/* bold header bar */}
        <div style={{ background: accent, padding: '8px 10px', flexShrink: 0 }}>
          <div style={{ height: 7, width: '60%', background: 'rgba(255,255,255,.9)', borderRadius: 2, marginBottom: 4 }} />
          <div style={{ height: 3.5, width: '40%', background: 'rgba(255,255,255,.55)', borderRadius: 2 }} />
        </div>
        {/* body */}
        <div style={{ flex: 1, padding: '7px 10px', display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ height: 4, width: '45%', background: accent, opacity: .6, borderRadius: 2 }} />
          {[90, 75, 85, 60, 70].map((w, i) => (
            <div key={i} style={{ height: 3, width: `${w}%`, background: '#e5e7eb', borderRadius: 2 }} />
          ))}
        </div>
      </div>
    )
  }

  if (id === 'academic') {
    return (
      <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 3, height: '100%', fontSize: 0 }}>
        <div style={{ height: 6, width: '70%', background: accent, borderRadius: 2 }} />
        <div style={{ height: 3.5, width: '55%', background: '#cbd5e1', borderRadius: 2 }} />
        <div style={{ height: 3, width: '80%', background: '#e5e7eb', borderRadius: 2 }} />
        <div style={{ height: 1, background: '#e5e7eb', margin: '3px 0' }} />
        <div style={{ height: 4.5, width: '35%', background: accent, opacity: .5, borderRadius: 2 }} />
        {[90, 80, 70, 85, 60].map((w, i) => (
          <div key={i} style={{ height: 3, width: `${w}%`, background: '#e5e7eb', borderRadius: 2 }} />
        ))}
      </div>
    )
  }

  if (id === 'trades') {
    return (
      <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 3, height: '100%', fontSize: 0 }}>
        <div style={{ height: 6, width: '60%', background: accent, borderRadius: 2 }} />
        <div style={{ height: 3.5, width: '45%', background: '#cbd5e1', borderRadius: 2 }} />
        <div style={{ height: 1, background: '#e5e7eb', margin: '3px 0' }} />
        {/* licence chips */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 2 }}>
          {['45%', '35%', '40%'].map((w, i) => (
            <div key={i} style={{ height: 12, width: w, background: accent, opacity: .18, borderRadius: 10 }} />
          ))}
        </div>
        {[90, 75, 80, 65].map((w, i) => (
          <div key={i} style={{ height: 3, width: `${w}%`, background: '#e5e7eb', borderRadius: 2 }} />
        ))}
      </div>
    )
  }

  if (id === 'compact') {
    return (
      <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 2.5, height: '100%', fontSize: 0 }}>
        <div style={{ height: 5.5, width: '55%', background: accent, borderRadius: 2 }} />
        <div style={{ display: 'flex', gap: 6 }}>
          <div style={{ height: 3, width: '30%', background: '#cbd5e1', borderRadius: 2 }} />
          <div style={{ height: 3, width: '25%', background: '#cbd5e1', borderRadius: 2 }} />
        </div>
        <div style={{ height: 1, background: accent, opacity: .3, margin: '2px 0' }} />
        {[95, 85, 80, 90, 75, 85, 70].map((w, i) => (
          <div key={i} style={{ height: 2.5, width: `${w}%`, background: '#e5e7eb', borderRadius: 2 }} />
        ))}
      </div>
    )
  }

  // classic (default)
  return (
    <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 3, height: '100%', fontSize: 0 }}>
      <div style={{ height: 7, width: '65%', background: accent, borderRadius: 2 }} />
      <div style={{ height: 3.5, width: '50%', background: '#cbd5e1', borderRadius: 2 }} />
      <div style={{ height: 1, background: accent, opacity: .35, margin: '3px 0' }} />
      <div style={{ height: 4, width: '30%', background: accent, opacity: .55, borderRadius: 2 }} />
      {[90, 80, 70, 95, 75, 60].map((w, i) => (
        <div key={i} style={{ height: 3, width: `${w}%`, background: '#e5e7eb', borderRadius: 2 }} />
      ))}
    </div>
  )
}

export default function TemplatePickerModal({ current, currentColor, onSelect, onClose }) {
  const [selected, setSelected] = useState(current)
  const [color, setColor] = useState(currentColor)
  const [customColor, setCustomColor] = useState(currentColor)

  function handleSwatch(c) { setColor(c); setCustomColor(c) }
  function handleCustomHex(e) {
    setCustomColor(e.target.value)
    if (/^#[0-9a-fA-F]{6}$/.test(e.target.value)) setColor(e.target.value)
  }

  return (
    <div
      className="modal-backdrop"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        className="modal"
        initial={{ opacity: 0, scale: .95, y: 12 }}
        animate={{ opacity: 1, scale: 1,   y: 0,  transition: { duration: .22, ease: [.4, 0, .2, 1] } }}
        exit={{    opacity: 0, scale: .97,  y: 8,  transition: { duration: .15 } }}
      >
        <div className="modal-header">
          <span className="modal-title">Choose a template</span>
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="template-grid">
          {TEMPLATES.map(t => (
            <div
              key={t.id}
              className={`template-card${selected === t.id ? ' selected' : ''}`}
              onClick={() => setSelected(t.id)}
            >
              {t.ats && <span className="ats-badge">ATS-safe</span>}
              <div className="template-check"><Check size={12} /></div>
              <div className="template-thumb">
                <TemplateMiniCV id={t.id} accent={color} />
              </div>
              <div className="template-info">
                <div className="template-name">{t.name}</div>
                <div className="template-desc">{t.desc}</div>
                <div className="template-domains">{t.domains}</div>
              </div>
            </div>
          ))}
        </div>

        <hr className="divider" />

        <div className="color-section">
          <div className="color-section-title">Accent colour</div>
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
          <div className="color-custom-row">
            <input
              type="color"
              value={color}
              onChange={e => { setColor(e.target.value); setCustomColor(e.target.value) }}
            />
            <input
              type="text"
              value={customColor}
              onChange={handleCustomHex}
              maxLength={7}
              placeholder="#4361ee"
            />
            <span className="color-custom-label">Custom hex</span>
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => onSelect(selected, color)}>
            <Check size={14} />
            Apply
          </button>
        </div>
      </motion.div>
    </div>
  )
}
