import { api } from '../api.js'

const DEVICE_KEY = 'cvo.device_id'
const claimedKey = (userId) => `cvo.bonus_claimed.${userId}`

function read(key) {
  try { return window.localStorage.getItem(key) } catch { return null }
}

function write(key, value) {
  try { window.localStorage.setItem(key, value) } catch { /* storage unavailable */ }
}

function randomId() {
  const bytes = new Uint8Array(16)
  window.crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

// Stable random id for this browser (letters/digits only, well under the 64 char limit).
export function deviceId() {
  let id = read(DEVICE_KEY)
  if (!id) {
    id = randomId()
    write(DEVICE_KEY, id)
  }
  return id
}

// Claim the signup bonus once per user, on the first session where the email is confirmed.
// Resolves to the server status, or null when nothing was attempted or the call failed.
export async function claimBonus(session) {
  const user = session && session.user
  if (!user || !user.email_confirmed_at) return null
  if (read(claimedKey(user.id))) return null
  try {
    const { data, ok } = await api.claimSignupBonus(session.access_token, deviceId())
    if (!ok) return null
    write(claimedKey(user.id), '1')
    return data.status
  } catch {
    return null
  }
}
