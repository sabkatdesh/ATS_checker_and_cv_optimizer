// Supabase redirects an expired or already-used confirmation link to /auth/callback with
// error params in the hash (or query). Read them once at module load, before the auth
// client consumes the URL, and expose a short constant notice (never the raw params).
export const EXPIRED_LINK_NOTICE =
  'This link has expired. Sign in to request a new verification email.'

export function readAuthLinkError(location) {
  if (!location || !location.pathname?.startsWith('/auth/callback')) return null
  const params = new URLSearchParams((location.hash || '').replace(/^#/, ''))
  const query = new URLSearchParams(location.search || '')
  const get = (key) => params.get(key) || query.get(key)
  if (get('error_code') === 'otp_expired' || get('error') === 'access_denied') {
    return EXPIRED_LINK_NOTICE
  }
  return null
}

const initialNotice = typeof window === 'undefined' ? null : readAuthLinkError(window.location)

export function authLinkNotice() {
  return initialNotice
}
