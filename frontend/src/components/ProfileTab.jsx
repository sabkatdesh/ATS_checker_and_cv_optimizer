import { useState, useEffect } from 'react'
import { api } from '../api.js'

const DOMAINS = [
  { value: 'general',   label: 'General' },
  { value: 'tech',      label: 'Technology' },
  { value: 'medical',   label: 'Medical / Healthcare' },
  { value: 'education', label: 'Education / Academic' },
  { value: 'trades',    label: 'Trades / Technical' },
  { value: 'finance',   label: 'Finance / Accounting' },
  { value: 'legal',     label: 'Legal' },
  { value: 'creative',  label: 'Creative / Design' },
]

const DOMAIN_OPTIONAL = {
  medical:   ['licenses', 'clinical_practice'],
  education: ['publications', 'awards'],
  trades:    ['licenses', 'trade_qualifications'],
  legal:     ['licenses'],
  creative:  ['awards'],
  finance:   ['awards'],
  tech:      ['projects'],
  general:   [],
}

function EntryList({ items, renderLabel, onRemove }) {
  const [open, setOpen] = useState(null)
  if (!items.length) return null
  return (
    <div style={{ marginBottom: 16 }}>
      {items.map((item, i) => (
        <div className="entry-card" key={i}>
          <div className="entry-card-head" onClick={() => setOpen(open === i ? null : i)}>
            <span>{renderLabel(item)}</span>
            <button
              className="btn btn-ghost"
              onClick={e => { e.stopPropagation(); onRemove(i) }}
              title="Remove"
            >
              ✕
            </button>
          </div>
          {open === i && (
            <div className="entry-card-body">
              {Object.entries(item).map(([k, v]) => (
                <div key={k} style={{ marginBottom: 4 }}>
                  <strong style={{ textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}: </strong>
                  {Array.isArray(v) ? v.join(', ') : String(v)}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function ProfileTab({ token }) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const [importText, setImportText] = useState('')
  const [importing, setImporting] = useState(false)

  // Basic fields
  const [form, setForm] = useState({
    full_name: '', email: '', phone: '', location: '',
    linkedin: '', github: '', portfolio: '', summary: '',
    domain: 'general', preferred_template: 'classic',
    accent_color: '#4361ee', bangla_mode: false,
  })

  // Skills
  const [skills, setSkills] = useState({ hard_skills: '', tools: '', frameworks: '', cloud_platforms: '', soft_skills: '' })

  // List sections
  const [experience, setExperience]         = useState([])
  const [education, setEducation]           = useState([])
  const [certifications, setCertifications] = useState([])
  const [projects, setProjects]             = useState([])
  const [licenses, setLicenses]             = useState([])
  const [publications, setPublications]     = useState([])
  const [awards, setAwards]                 = useState([])

  // Add-entry form state (experience)
  const [newExp, setNewExp] = useState({ job_title: '', company: '', start_date: '', end_date: '', responsibilities: '', achievements: '' })
  const [newEdu, setNewEdu] = useState({ degree: '', field_of_study: '', institution: '', graduation_year: '' })
  const [newCert, setNewCert] = useState({ name: '', issuer: '', year: '' })
  const [newProj, setNewProj] = useState({ title: '', description: '', technologies: '' })
  const [newLic, setNewLic] = useState({ name: '', authority: '', number: '', expiry: '' })
  const [newPub, setNewPub] = useState({ title: '', authors: '', journal: '', year: '' })
  const [newAward, setNewAward] = useState({ title: '', issuer: '', year: '' })

  useEffect(() => {
    api.getProfile(token).then(({ data }) => {
      const p = data.profile || {}
      const s = p.skills || {}
      setForm(f => ({
        ...f,
        full_name: p.full_name || '', email: p.email || '', phone: p.phone || '',
        location: p.location || '', linkedin: p.linkedin || '', github: p.github || '',
        portfolio: p.portfolio || '', summary: p.summary || '',
        domain: p.domain || 'general', preferred_template: p.preferred_template || 'classic',
        accent_color: p.accent_color || '#4361ee', bangla_mode: !!p.bangla_mode,
      }))
      setSkills({
        hard_skills:    (s.hard_skills || []).join(', '),
        tools:          (s.tools || []).join(', '),
        frameworks:     (s.frameworks || []).join(', '),
        cloud_platforms:(s.cloud_platforms || []).join(', '),
        soft_skills:    (s.soft_skills || []).join(', '),
      })
      setExperience(p.experience || [])
      setEducation(p.education || [])
      setCertifications(p.certifications || [])
      setProjects(p.projects || [])
      setLicenses(p.licenses || [])
      setPublications(p.publications || [])
      setAwards(p.awards || [])
      setLoading(false)
    })
  }, [token])

  function f(key) { return { value: form[key], onChange: e => setForm(p => ({ ...p, [key]: e.target.value })) } }
  function sk(key) { return { value: skills[key], onChange: e => setSkills(p => ({ ...p, [key]: e.target.value })) } }
  function parseCSV(s) { return s.split(',').map(x => x.trim()).filter(Boolean) }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    setError('')

    const payload = {
      ...form,
      skills: {
        hard_skills:    parseCSV(skills.hard_skills),
        tools:          parseCSV(skills.tools),
        frameworks:     parseCSV(skills.frameworks),
        cloud_platforms:parseCSV(skills.cloud_platforms),
        soft_skills:    parseCSV(skills.soft_skills),
      },
      experience, education, certifications, projects,
      licenses, publications, awards,
    }

    const { ok } = await api.saveProfile(token, payload)
    setSaving(false)
    if (ok) setMsg('Profile saved.')
    else setError('Could not save. Check that the API server is running.')
  }

  async function handleImport(e) {
    e.preventDefault()
    if (importText.trim().length < 100) { setError('Paste at least 100 characters of CV text.'); return }
    setImporting(true)
    setError('')
    const { data, ok } = await api.importCV(token, importText.trim())
    setImporting(false)
    if (!ok) { setError('CV parsing failed.'); return }
    const p = data.profile || {}
    const s = p.skills || {}
    setForm(f => ({
      ...f, ...p,
      domain: p.domain || 'general',
      bangla_mode: !!p.bangla_mode,
    }))
    setSkills({
      hard_skills:    (s.hard_skills || []).join(', '),
      tools:          (s.tools || []).join(', '),
      frameworks:     (s.frameworks || []).join(', '),
      cloud_platforms:(s.cloud_platforms || []).join(', '),
      soft_skills:    (s.soft_skills || []).join(', '),
    })
    if (p.experience)     setExperience(p.experience)
    if (p.education)      setEducation(p.education)
    if (p.certifications) setCertifications(p.certifications)
    if (p.projects)       setProjects(p.projects)
    setMsg('CV imported. Review the fields below and save.')
  }

  const optionalSections = DOMAIN_OPTIONAL[form.domain] || []
  const showLicenses      = optionalSections.includes('licenses')
  const showPublications  = optionalSections.includes('publications')
  const showProjects      = optionalSections.includes('projects') || form.domain === 'tech' || form.domain === 'general'
  const showAwards        = optionalSections.includes('awards')
  const showClinical      = optionalSections.includes('clinical_practice')
  const showTrade         = optionalSections.includes('trade_qualifications')

  if (loading) return <div className="page" style={{ color: 'var(--muted)' }}>Loading profile…</div>

  return (
    <div className="page">
      <h2 className="page-title">My profile</h2>
      <p className="page-sub">Fill this in once. It's used every time you generate a CV.</p>

      {msg   && <div className="alert alert-success">{msg}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {/* ── Import from CV text ─────────────────────────────────────────── */}
      <details style={{ marginBottom: 24 }}>
        <summary style={{ cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'var(--accent)', userSelect: 'none' }}>
          Import from existing CV
        </summary>
        <div style={{ marginTop: 12 }}>
          <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 10 }}>
            Paste your existing CV text and we'll pre-fill the fields below.
          </p>
          <div className="field">
            <textarea
              rows={7}
              placeholder="Paste CV text here..."
              value={importText}
              onChange={e => setImportText(e.target.value)}
            />
          </div>
          <button className="btn btn-secondary" onClick={handleImport} disabled={importing}>
            {importing ? 'Importing…' : 'Auto-fill from CV'}
          </button>
        </div>
      </details>

      <form onSubmit={handleSave}>
        {/* ── Domain ───────────────────────────────────────────────────── */}
        <div className="section-title">Profession</div>
        <div className="field-row" style={{ marginBottom: 20 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Your field</label>
            <select value={form.domain} onChange={e => setForm(p => ({ ...p, domain: e.target.value }))}>
              {DOMAINS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
            <div className="field-hint">Determines which sections are shown and how the CV is structured.</div>
          </div>
        </div>

        {/* ── Personal info ─────────────────────────────────────────────── */}
        <div className="section-title">Personal information</div>
        <div className="field-row">
          <div className="field"><label>Full name</label><input type="text" {...f('full_name')} /></div>
          <div className="field"><label>Email</label><input type="email" {...f('email')} /></div>
        </div>
        <div className="field-row">
          <div className="field"><label>Phone</label><input type="tel" {...f('phone')} /></div>
          <div className="field"><label>Location</label><input type="text" {...f('location')} placeholder="City, Country" /></div>
        </div>
        <div className="field-row">
          <div className="field"><label>LinkedIn</label><input type="url" {...f('linkedin')} placeholder="https://linkedin.com/in/…" /></div>
          <div className="field"><label>GitHub</label><input type="url" {...f('github')} placeholder="https://github.com/…" /></div>
        </div>
        <div className="field">
          <label>Portfolio / website</label>
          <input type="url" {...f('portfolio')} placeholder="https://…" />
        </div>

        {/* ── Summary ───────────────────────────────────────────────────── */}
        <hr className="divider" />
        <div className="section-title">Professional summary</div>
        <div className="field">
          <textarea rows={4} {...f('summary')} placeholder="Write 2–4 sentences about your background, key skills, and what you're looking for." />
        </div>

        {/* ── Skills ───────────────────────────────────────────────────── */}
        <hr className="divider" />
        <div className="section-title">Skills</div>
        <div className="field"><label>Hard skills</label><input type="text" {...sk('hard_skills')} placeholder="Python, Data Analysis, SQL" /></div>
        <div className="field"><label>Tools</label><input type="text" {...sk('tools')} placeholder="Git, Docker, Figma" /></div>
        <div className="field"><label>Frameworks</label><input type="text" {...sk('frameworks')} placeholder="React, Django, TensorFlow" /></div>
        {(form.domain === 'tech' || form.domain === 'general') && (
          <div className="field"><label>Cloud platforms</label><input type="text" {...sk('cloud_platforms')} placeholder="AWS, Azure, GCP" /></div>
        )}
        <div className="field"><label>Soft skills</label><input type="text" {...sk('soft_skills')} placeholder="Leadership, Communication" /></div>
        <p className="field-hint" style={{ marginBottom: 16 }}>Separate items with commas.</p>

        {/* ── Work experience ───────────────────────────────────────────── */}
        <hr className="divider" />
        <div className="section-title">Work experience</div>
        <EntryList
          items={experience}
          renderLabel={e => `${e.job_title} at ${e.company}`}
          onRemove={i => setExperience(prev => prev.filter((_, j) => j !== i))}
        />
        <details>
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>
            Add experience
          </summary>
          <div className="card">
            <div className="field-row">
              <div className="field"><label>Job title</label><input value={newExp.job_title} onChange={e => setNewExp(p=>({...p,job_title:e.target.value}))} /></div>
              <div className="field"><label>Company</label><input value={newExp.company} onChange={e => setNewExp(p=>({...p,company:e.target.value}))} /></div>
            </div>
            <div className="field-row">
              <div className="field"><label>Start date</label><input placeholder="Jan 2022" value={newExp.start_date} onChange={e => setNewExp(p=>({...p,start_date:e.target.value}))} /></div>
              <div className="field"><label>End date</label><input placeholder="Dec 2023 or Present" value={newExp.end_date} onChange={e => setNewExp(p=>({...p,end_date:e.target.value}))} /></div>
            </div>
            <div className="field"><label>Responsibilities (one per line)</label><textarea rows={3} value={newExp.responsibilities} onChange={e => setNewExp(p=>({...p,responsibilities:e.target.value}))} /></div>
            <div className="field"><label>Achievements (one per line)</label><textarea rows={3} value={newExp.achievements} onChange={e => setNewExp(p=>({...p,achievements:e.target.value}))} /></div>
            <button type="button" className="btn btn-secondary" onClick={() => {
              if (!newExp.job_title || !newExp.company) return
              setExperience(prev => [...prev, {
                job_title: newExp.job_title, company: newExp.company,
                start_date: newExp.start_date, end_date: newExp.end_date,
                responsibilities: newExp.responsibilities.split('\n').filter(Boolean),
                achievements: newExp.achievements.split('\n').filter(Boolean),
              }])
              setNewExp({ job_title:'', company:'', start_date:'', end_date:'', responsibilities:'', achievements:'' })
            }}>Add</button>
          </div>
        </details>

        {/* ── Education ─────────────────────────────────────────────────── */}
        <hr className="divider" />
        <div className="section-title">Education</div>
        <EntryList
          items={education}
          renderLabel={e => `${e.degree} — ${e.institution}`}
          onRemove={i => setEducation(prev => prev.filter((_, j) => j !== i))}
        />
        <details>
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>
            Add education
          </summary>
          <div className="card">
            <div className="field-row">
              <div className="field"><label>Degree</label><input placeholder="BSc" value={newEdu.degree} onChange={e => setNewEdu(p=>({...p,degree:e.target.value}))} /></div>
              <div className="field"><label>Field of study</label><input placeholder="Computer Science" value={newEdu.field_of_study} onChange={e => setNewEdu(p=>({...p,field_of_study:e.target.value}))} /></div>
            </div>
            <div className="field-row">
              <div className="field"><label>Institution</label><input value={newEdu.institution} onChange={e => setNewEdu(p=>({...p,institution:e.target.value}))} /></div>
              <div className="field"><label>Graduation year</label><input placeholder="2021" value={newEdu.graduation_year} onChange={e => setNewEdu(p=>({...p,graduation_year:e.target.value}))} /></div>
            </div>
            <button type="button" className="btn btn-secondary" onClick={() => {
              if (!newEdu.degree || !newEdu.institution) return
              setEducation(prev => [...prev, { ...newEdu }])
              setNewEdu({ degree:'', field_of_study:'', institution:'', graduation_year:'' })
            }}>Add</button>
          </div>
        </details>

        {/* ── Certifications ────────────────────────────────────────────── */}
        <hr className="divider" />
        <div className="section-title">Certifications</div>
        <EntryList
          items={certifications}
          renderLabel={c => `${c.name} — ${c.issuer}`}
          onRemove={i => setCertifications(prev => prev.filter((_, j) => j !== i))}
        />
        <details>
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>
            Add certification
          </summary>
          <div className="card">
            <div className="field-row">
              <div className="field"><label>Name</label><input value={newCert.name} onChange={e => setNewCert(p=>({...p,name:e.target.value}))} /></div>
              <div className="field"><label>Issuer</label><input placeholder="AWS, Google…" value={newCert.issuer} onChange={e => setNewCert(p=>({...p,issuer:e.target.value}))} /></div>
            </div>
            <div className="field"><label>Year</label><input placeholder="2023" value={newCert.year} onChange={e => setNewCert(p=>({...p,year:e.target.value}))} style={{ maxWidth: 120 }} /></div>
            <button type="button" className="btn btn-secondary" onClick={() => {
              if (!newCert.name) return
              setCertifications(prev => [...prev, { ...newCert }])
              setNewCert({ name:'', issuer:'', year:'' })
            }}>Add</button>
          </div>
        </details>

        {/* ── Projects (tech/general) ───────────────────────────────────── */}
        {showProjects && (
          <>
            <hr className="divider" />
            <div className="section-title">Projects</div>
            <EntryList
              items={projects}
              renderLabel={p => p.title}
              onRemove={i => setProjects(prev => prev.filter((_, j) => j !== i))}
            />
            <details>
              <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>
                Add project
              </summary>
              <div className="card">
                <div className="field"><label>Title</label><input value={newProj.title} onChange={e => setNewProj(p=>({...p,title:e.target.value}))} /></div>
                <div className="field"><label>Description</label><textarea rows={3} value={newProj.description} onChange={e => setNewProj(p=>({...p,description:e.target.value}))} /></div>
                <div className="field"><label>Technologies</label><input placeholder="Python, React, Docker" value={newProj.technologies} onChange={e => setNewProj(p=>({...p,technologies:e.target.value}))} /></div>
                <button type="button" className="btn btn-secondary" onClick={() => {
                  if (!newProj.title) return
                  setProjects(prev => [...prev, { title:newProj.title, description:newProj.description, technologies: newProj.technologies.split(',').map(x=>x.trim()).filter(Boolean) }])
                  setNewProj({ title:'', description:'', technologies:'' })
                }}>Add</button>
              </div>
            </details>
          </>
        )}

        {/* ── Licenses (medical/trades/legal) ───────────────────────────── */}
        {showLicenses && (
          <>
            <hr className="divider" />
            <div className="section-title">Licenses &amp; registrations</div>
            <EntryList items={licenses} renderLabel={l => l.name} onRemove={i => setLicenses(prev => prev.filter((_,j)=>j!==i))} />
            <details>
              <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>Add license</summary>
              <div className="card">
                <div className="field-row">
                  <div className="field"><label>License / registration name</label><input value={newLic.name} onChange={e => setNewLic(p=>({...p,name:e.target.value}))} /></div>
                  <div className="field"><label>Issuing authority</label><input value={newLic.authority} onChange={e => setNewLic(p=>({...p,authority:e.target.value}))} /></div>
                </div>
                <div className="field-row">
                  <div className="field"><label>Number (optional)</label><input value={newLic.number} onChange={e => setNewLic(p=>({...p,number:e.target.value}))} /></div>
                  <div className="field"><label>Expiry (optional)</label><input placeholder="Dec 2026" value={newLic.expiry} onChange={e => setNewLic(p=>({...p,expiry:e.target.value}))} /></div>
                </div>
                <button type="button" className="btn btn-secondary" onClick={() => {
                  if (!newLic.name) return
                  setLicenses(prev => [...prev, { ...newLic }])
                  setNewLic({ name:'', authority:'', number:'', expiry:'' })
                }}>Add</button>
              </div>
            </details>
          </>
        )}

        {/* ── Publications (education/medical) ──────────────────────────── */}
        {showPublications && (
          <>
            <hr className="divider" />
            <div className="section-title">Publications</div>
            <EntryList items={publications} renderLabel={p => p.title} onRemove={i => setPublications(prev => prev.filter((_,j)=>j!==i))} />
            <details>
              <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>Add publication</summary>
              <div className="card">
                <div className="field"><label>Title</label><input value={newPub.title} onChange={e => setNewPub(p=>({...p,title:e.target.value}))} /></div>
                <div className="field-row">
                  <div className="field"><label>Authors</label><input value={newPub.authors} onChange={e => setNewPub(p=>({...p,authors:e.target.value}))} /></div>
                  <div className="field"><label>Journal / venue</label><input value={newPub.journal} onChange={e => setNewPub(p=>({...p,journal:e.target.value}))} /></div>
                </div>
                <div className="field"><label>Year</label><input placeholder="2023" value={newPub.year} onChange={e => setNewPub(p=>({...p,year:e.target.value}))} style={{ maxWidth: 120 }} /></div>
                <button type="button" className="btn btn-secondary" onClick={() => {
                  if (!newPub.title) return
                  setPublications(prev => [...prev, { ...newPub }])
                  setNewPub({ title:'', authors:'', journal:'', year:'' })
                }}>Add</button>
              </div>
            </details>
          </>
        )}

        {/* ── Awards ────────────────────────────────────────────────────── */}
        {showAwards && (
          <>
            <hr className="divider" />
            <div className="section-title">Awards &amp; honours</div>
            <EntryList items={awards} renderLabel={a => a.title} onRemove={i => setAwards(prev => prev.filter((_,j)=>j!==i))} />
            <details>
              <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 12, userSelect: 'none' }}>Add award</summary>
              <div className="card">
                <div className="field-row">
                  <div className="field"><label>Title</label><input value={newAward.title} onChange={e => setNewAward(p=>({...p,title:e.target.value}))} /></div>
                  <div className="field"><label>Issuer</label><input value={newAward.issuer} onChange={e => setNewAward(p=>({...p,issuer:e.target.value}))} /></div>
                </div>
                <div className="field"><label>Year</label><input placeholder="2023" value={newAward.year} onChange={e => setNewAward(p=>({...p,year:e.target.value}))} style={{ maxWidth: 120 }} /></div>
                <button type="button" className="btn btn-secondary" onClick={() => {
                  if (!newAward.title) return
                  setAwards(prev => [...prev, { ...newAward }])
                  setNewAward({ title:'', issuer:'', year:'' })
                }}>Add</button>
              </div>
            </details>
          </>
        )}

        {/* ── Preferences ───────────────────────────────────────────────── */}
        <hr className="divider" />
        <div className="section-title">CV preferences</div>
        <div className="field-row">
          <div className="field">
            <label>Default template</label>
            <select value={form.preferred_template} onChange={e => setForm(p=>({...p,preferred_template:e.target.value}))}>
              <option value="classic">Classic</option>
              <option value="modern">Modern</option>
              <option value="compact">Compact</option>
              <option value="academic">Academic</option>
              <option value="trades">Trades</option>
              <option value="creative">Creative</option>
            </select>
          </div>
          <div className="field">
            <label>Accent colour</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input type="color" value={form.accent_color} onChange={e => setForm(p=>({...p,accent_color:e.target.value}))} style={{ width: 36, height: 32, padding: 2, border:'1px solid var(--border)', borderRadius: 4 }} />
              <input type="text" value={form.accent_color} onChange={e => setForm(p=>({...p,accent_color:e.target.value}))} style={{ width: 90, padding:'5px 8px', border:'1px solid var(--border)', borderRadius:4, fontSize:13 }} maxLength={7} />
            </div>
          </div>
        </div>
        <div className="field">
          <label style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer' }}>
            <input type="checkbox" checked={form.bangla_mode} onChange={e => setForm(p=>({...p,bangla_mode:e.target.checked}))} />
            Include Bengali text support (Hind Siliguri font)
          </label>
          <div className="field-hint">Enable if your CV contains Bangla text.</div>
        </div>

        <hr className="divider" />
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save profile'}
        </button>
      </form>
    </div>
  )
}
