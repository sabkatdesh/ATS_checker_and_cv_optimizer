# Auth setup (remote Supabase project)

`supabase/config.toml` only drives the local CLI stack and `supabase config push`.
Nothing in it changes a remote project by itself. Every step below is a remote
dashboard or `config push` action and needs the owner's explicit approval before it
is run. No secret belongs in this repository: `config.toml` holds only `env(NAME)`
references, and real values live in the dashboard or the deployment secret store.

## Why custom SMTP is needed

The built-in Supabase mailer only delivers to addresses of your project's team
members and is heavily rate limited. Real users will not receive confirmation
emails until a custom SMTP provider is configured, so do this before any public
signup.

## Email confirmation and SMTP (Resend)

1. Create a Resend account and add your sending domain.
2. Publish the DNS records Resend shows for the domain: SPF (TXT), DKIM (CNAME or
   TXT) and, recommended, a DMARC TXT record. Wait until the domain shows as verified.
3. Create a Resend API key restricted to sending.
4. In the Supabase dashboard open Authentication, then SMTP settings, and enter:
   host `smtp.resend.com`, port `465`, user `resend`, password = the API key, a
   sender address on the verified domain and a sender name.
   Alternatively set `[auth.email.smtp] enabled = true` in `config.toml`, export
   `SUPABASE_AUTH_SMTP_PASS` in your shell and run `supabase config push`.
5. Confirm "Confirm email" is on, OTP expiry is 3600 s, and the minimum interval
   between emails is 60 s (these match `config.toml`).
6. Raise the "emails per hour" rate limit to a value suited to expected traffic.

## Redirect URLs

Under Authentication, URL configuration, set the Site URL to the production frontend
origin and add the callback URLs: `http://localhost:5173/auth/callback` for local
development and `https://<your-frontend-domain>/auth/callback` for production.

## SPA fallback for /auth/callback

Confirmation and OAuth links land on `<frontend-origin>/auth/callback`. The frontend
host must serve `index.html` for that path (a single-page-app fallback), otherwise
the link returns a 404 before the session in the URL can be read.

## Google sign-in

1. In Google Cloud Console configure the OAuth consent screen (app name, support
   email, authorized domains) and publish it when ready for external users.
2. Create an OAuth client of type "Web application".
3. Add this authorized redirect URI:
   `https://<project-ref>.supabase.co/auth/v1/callback`
   (and, for a local CLI stack, `http://127.0.0.1:54321/auth/v1/callback`).
4. In the Supabase dashboard, Authentication, Sign In / Providers, enable Google and
   paste the client ID and client secret. For `config push`, export
   `SUPABASE_AUTH_GOOGLE_CLIENT_ID` and `SUPABASE_AUTH_GOOGLE_SECRET` and set
   `[auth.external.google] enabled = true`.
5. Build the frontend with `VITE_AUTH_GOOGLE=1` so the Google button appears.

## Cloudflare Turnstile (captcha)

1. Create a Turnstile widget in the Cloudflare dashboard for the frontend domains.
2. In Supabase, Authentication, Attack Protection, enable captcha with provider
   Turnstile and paste the widget secret. For `config push`, export
   `SUPABASE_AUTH_CAPTCHA_SECRET`.
3. Build the frontend with `VITE_TURNSTILE_SITE_KEY=<site key>`. When unset, the
   widget and the Turnstile script are not loaded.
4. Captcha is verified by Supabase Auth on signup, password sign-in and the
   confirmation resend, so the frontend sends a fresh single-use token for each.
5. Local CLI stack: `config.toml` enables captcha, so `supabase start` needs
   `SUPABASE_AUTH_CAPTCHA_SECRET` exported. Use Cloudflare's public always-pass test
   secret `1x0000000000000000000000000000000AA` and the matching test site key
   `1x00000000000000000000AA` for `VITE_TURNSTILE_SITE_KEY`. Never use test keys in
   production.

## JWT signing keys (ES256)

The backend verifies tokens locally against the project's JWKS. In the dashboard,
Project Settings, JWT Signing Keys, create or migrate to an asymmetric key (ES256),
then rotate so it is the active signing key. Keep the legacy HS256 secret only as
long as old tokens must stay valid, then revoke it. The backend reads the key set
from `<project-url>/auth/v1/.well-known/jwks.json` (cached for 10 minutes), so no
key material is ever stored in this repository.

## Environment variable names

| Name | Used by |
| --- | --- |
| `SUPABASE_AUTH_GOOGLE_CLIENT_ID`, `SUPABASE_AUTH_GOOGLE_SECRET` | Google provider |
| `SUPABASE_AUTH_CAPTCHA_SECRET` | Turnstile secret |
| `SUPABASE_AUTH_SMTP_PASS` | Resend API key |
| `VITE_TURNSTILE_SITE_KEY` | Frontend captcha widget |
| `VITE_AUTH_GOOGLE` | Frontend Google button (`1` to show) |
