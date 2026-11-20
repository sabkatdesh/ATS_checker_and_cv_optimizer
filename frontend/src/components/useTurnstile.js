import { useEffect, useRef, useState } from 'react'

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
export const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''

function loadScript() {
  if (window.turnstile) return Promise.resolve()
  return new Promise((resolve, reject) => {
    // A previously errored tag never fires load again: drop it and retry fresh.
    const old = document.querySelector(`script[src="${SCRIPT_SRC}"]`)
    if (old && old.dataset.failed) old.remove()
    let el = document.querySelector(`script[src="${SCRIPT_SRC}"]`)
    if (!el) {
      el = document.createElement('script')
      el.src = SCRIPT_SRC
      el.async = true
      document.head.appendChild(el)
    }
    el.addEventListener('load', resolve, { once: true })
    el.addEventListener('error', () => { el.dataset.failed = '1'; reject(new Error('turnstile')) }, { once: true })
  })
}

// Renders a Turnstile widget into containerRef when a site key is configured.
// The script is only loaded when the key is set. Returns the current token
// (null until solved), a reset function, and loadError/retry for script failures.
// `active` is any truthy key; changing it re-renders the widget into the new container.
export function useTurnstile(active) {
  const containerRef = useRef(null)
  const widgetId = useRef(null)
  const [token, setToken] = useState(null)
  const [loadError, setLoadError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !active) return undefined
    let cancelled = false
    setLoadError(false)
    loadScript().then(() => {
      if (cancelled || !containerRef.current || !window.turnstile) return
      widgetId.current = window.turnstile.render(containerRef.current, {
        sitekey: TURNSTILE_SITE_KEY,
        callback: setToken,
        'expired-callback': () => setToken(null),
        'error-callback': () => setToken(null),
      })
    }).catch(() => { if (!cancelled) setLoadError(true) })
    return () => {
      cancelled = true
      if (widgetId.current != null && window.turnstile) window.turnstile.remove(widgetId.current)
      widgetId.current = null
      setToken(null)
    }
  }, [active, attempt])

  function reset() {
    if (widgetId.current != null && window.turnstile) window.turnstile.reset(widgetId.current)
    setToken(null)
  }

  const retry = () => setAttempt(n => n + 1)

  return { containerRef, token, reset, retry, loadError, enabled: Boolean(TURNSTILE_SITE_KEY) }
}
