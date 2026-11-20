export const CAPTCHA_LOAD_ERROR = 'Could not load the security check. Disable blockers or try again.'

// Widget container plus the load-failure message with a retry button.
export default function CaptchaBox({ captcha }) {
  if (!captcha.enabled) return null
  return (
    <div style={{ margin: '8px 0' }}>
      <div ref={captcha.containerRef} />
      {captcha.loadError && (
        <div className="alert alert-error">
          {CAPTCHA_LOAD_ERROR}{' '}
          <button type="button" className="btn" onClick={captcha.retry}>Retry</button>
        </div>
      )}
    </div>
  )
}
