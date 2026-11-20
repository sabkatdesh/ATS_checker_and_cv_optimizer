import { useEffect, useRef, useState } from 'react'

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
export const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''

function loadScript() {
  if (window.turnstile) return Promise.resolve()
  return new Promise((resolve, reject) => {
    let el = document.querySelector(`script[src="${SCRIPT_SRC}"]`)
    if (!el) {
      el = document.createElement('script')
      el.src = SCRIPT_SRC
      el.async = true
      document.head.appendChild(el)
    }
    el.addEventListener('load', resolve, { once: true })
    el.addEventListener('error', reject, { once: true })
  })
}

// Renders a Turnstile widget into containerRef when a site key is configured.
// The script is only loaded when the key is set. Returns the current token
// (null until solved) and a reset function.
export function useTurnstile(active) {
  const containerRef = useRef(null)
  const widgetId = useRef(null)
  const [token, setToken] = useState(null)

  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !active) return undefined
    let cancelled = false
    loadScript().then(() => {
      if (cancelled || !containerRef.current || !window.turnstile) return
      widgetId.current = window.turnstile.render(containerRef.current, {
        sitekey: TURNSTILE_SITE_KEY,
        callback: setToken,
        'expired-callback': () => setToken(null),
        'error-callback': () => setToken(null),
      })
    }).catch(() => {})
    return () => {
      cancelled = true
      if (widgetId.current != null && window.turnstile) window.turnstile.remove(widgetId.current)
      widgetId.current = null
      setToken(null)
    }
  }, [active])

  function reset() {
    if (widgetId.current != null && window.turnstile) window.turnstile.reset(widgetId.current)
    setToken(null)
  }

  return { containerRef, token, reset, enabled: Boolean(TURNSTILE_SITE_KEY) }
}
