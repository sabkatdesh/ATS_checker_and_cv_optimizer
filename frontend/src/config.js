import { createClient } from '@supabase/supabase-js'
// Imported first so it reads the callback URL before the auth client handles it.
import './lib/authLinkError.js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  console.error(
    'Missing Supabase env vars. Copy .env.example to .env and fill in your project credentials.'
  )
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export const authCallbackUrl = () => window.location.origin + "/auth/callback"
