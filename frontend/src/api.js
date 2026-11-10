const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function headers(token) {
  const h = { 'Content-Type': 'application/json' }
  if (token) h.Authorization = `Bearer ${token}`
  return h
}

async function request(method, path, token, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(token),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  return { data, status: res.status, ok: res.ok }
}

export const api = {
  getProfile: (token) => request('GET', '/profile', token),
  saveProfile: (token, body) => request('POST', '/profile', token, body),
  importCV: (token, cv_text) => request('POST', '/profile/import-cv', token, { cv_text }),

  startSession: (token, body) => request('POST', '/sessions/start', token, body),
  getStatus: (token, threadId) => request('GET', `/sessions/${threadId}/status`, token),
  replyHitl: (token, threadId, user_qna) =>
    request('POST', `/sessions/${threadId}/reply`, token, { user_qna }),
  submitCoverLetterOptions: (token, threadId, tone, length) =>
    request('POST', `/sessions/${threadId}/cover-letter-options`, token, { tone, length }),
  saveCoverLetter: (token, threadId, text) =>
    request('POST', `/sessions/${threadId}/cover-letter`, token, { text }),
  getSessions: (token) => request('GET', '/sessions', token),

  getTemplates: () => request('GET', '/templates', null),

  getSettings: (token) => request('GET', '/settings', token),
  saveSettings: (token, body) => request('POST', '/settings', token, body),

  getBalance: (token) => request('GET', '/billing/balance', token),
  getBillingHistory: (token) => request('GET', '/billing/history', token),
}
