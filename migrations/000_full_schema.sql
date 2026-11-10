-- ============================================================
-- CV Optimizer — Full Database Schema (fresh install)
-- Run once in Supabase: Dashboard → SQL Editor → Run All
-- ============================================================


-- ── cv_profiles ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cv_profiles (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,

  -- contact
  full_name   TEXT,
  email       TEXT,
  phone       TEXT,
  location    TEXT,
  linkedin    TEXT,
  github      TEXT,
  portfolio   TEXT,

  -- narrative
  summary     TEXT,

  -- structured blocks (stored as JSONB arrays/objects)
  skills              JSONB DEFAULT '{}'::JSONB,
  experience          JSONB DEFAULT '[]'::JSONB,
  education           JSONB DEFAULT '[]'::JSONB,
  projects            JSONB DEFAULT '[]'::JSONB,
  certifications      JSONB DEFAULT '[]'::JSONB,

  -- universal / domain-specific blocks
  domain              TEXT  DEFAULT 'general',
  licenses            JSONB DEFAULT '[]'::JSONB,
  publications        JSONB DEFAULT '[]'::JSONB,
  clinical_practice   JSONB DEFAULT '[]'::JSONB,
  trade_qualifications JSONB DEFAULT '[]'::JSONB,
  languages           JSONB DEFAULT '[]'::JSONB,
  volunteering        JSONB DEFAULT '[]'::JSONB,
  awards              JSONB DEFAULT '[]'::JSONB,
  references_available BOOLEAN DEFAULT FALSE,

  -- appearance preferences
  preferred_template  TEXT    DEFAULT 'classic',
  accent_color        TEXT    DEFAULT '#4361ee',
  bangla_mode         BOOLEAN DEFAULT FALSE,

  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ── cv_sessions ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cv_sessions (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  thread_id   TEXT NOT NULL UNIQUE,

  job_description TEXT,
  status          TEXT DEFAULT 'running',
  -- status values: running | waiting_hitl | waiting_cover_letter | done | failed

  domain          TEXT,
  template_id     TEXT DEFAULT 'classic',

  -- scoring
  ats_score         INTEGER,
  semantic_score    INTEGER,
  improvement_score INTEGER,

  -- generated output
  structured_cv     JSONB,
  pdf_url           TEXT,

  -- eligibility gate
  eligibility_score INTEGER,
  gaps              JSONB DEFAULT '[]'::JSONB,

  -- HITL interrupt
  hitl_question TEXT,

  -- cover letter
  cover_letter_requested  BOOLEAN DEFAULT FALSE,
  cover_letter_tone       TEXT,     -- formal | conversational
  cover_letter_length     TEXT,     -- short | standard
  cover_letter_text       TEXT,
  cover_letter_pdf_url    TEXT,

  -- token cost tracking
  token_cost_input   INTEGER DEFAULT 0,
  token_cost_output  INTEGER DEFAULT 0,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ── cv_templates ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cv_templates (
  id                    TEXT PRIMARY KEY,
  name                  TEXT NOT NULL,
  description           TEXT,
  ats_safe              BOOLEAN  DEFAULT TRUE,
  recommended_domains   TEXT[]   DEFAULT '{}',
  preview_image_url     TEXT,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Seed the 6 built-in templates
INSERT INTO cv_templates (id, name, description, ats_safe, recommended_domains) VALUES
  ('classic',  'Classic',   'Clean two-column layout. ATS-safe, widely accepted.',         TRUE,  ARRAY['general','finance','legal','education']),
  ('modern',   'Modern',    'Bold header, accent sidebar. Professional and eye-catching.',  FALSE, ARRAY['tech','creative','marketing']),
  ('compact',  'Compact',   'Dense single-page layout for experienced professionals.',      TRUE,  ARRAY['general','tech','finance']),
  ('academic', 'Academic',  'Publications, research, and citations front and center.',      TRUE,  ARRAY['education','research','medical']),
  ('trades',   'Trades',    'Certifications, licenses, and site experience highlighted.',   TRUE,  ARRAY['trades','engineering','construction']),
  ('creative', 'Creative',  'Portfolio-ready. Full-bleed accents, project showcase.',       FALSE, ARRAY['creative','design','media'])
ON CONFLICT (id) DO NOTHING;


-- ── user_settings ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,

  default_template          TEXT    DEFAULT 'classic',
  accent_color              TEXT    DEFAULT '#4361ee',
  bangla_mode               BOOLEAN DEFAULT FALSE,
  cover_letter_default_tone TEXT    DEFAULT 'formal',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ── coin_balance ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coin_balance (
  id         BIGSERIAL PRIMARY KEY,
  user_id    UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  balance    INTEGER DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ── coin_transactions ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coin_transactions (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  amount      INTEGER NOT NULL,
  type        TEXT    NOT NULL,   -- purchase | charge | refund
  description TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================
-- Row-Level Security (enable for all tables)
-- ============================================================

ALTER TABLE cv_profiles        ENABLE ROW LEVEL SECURITY;
ALTER TABLE cv_sessions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE cv_templates       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE coin_balance       ENABLE ROW LEVEL SECURITY;
ALTER TABLE coin_transactions  ENABLE ROW LEVEL SECURITY;

-- Drop existing policies first (safe to re-run)
DROP POLICY IF EXISTS "Own profile only"      ON cv_profiles;
DROP POLICY IF EXISTS "Own sessions only"     ON cv_sessions;
DROP POLICY IF EXISTS "Templates read-only"   ON cv_templates;
DROP POLICY IF EXISTS "Own settings only"     ON user_settings;
DROP POLICY IF EXISTS "Own balance only"      ON coin_balance;
DROP POLICY IF EXISTS "Own transactions only" ON coin_transactions;

-- cv_profiles: users can only see/edit their own row
CREATE POLICY "Own profile only" ON cv_profiles
  FOR ALL USING (auth.uid() = user_id);

-- cv_sessions: users can only see/edit their own sessions
CREATE POLICY "Own sessions only" ON cv_sessions
  FOR ALL USING (auth.uid() = user_id);

-- cv_templates: read-only for all authenticated users
CREATE POLICY "Templates read-only" ON cv_templates
  FOR SELECT USING (TRUE);

-- user_settings: users can only see/edit their own settings
CREATE POLICY "Own settings only" ON user_settings
  FOR ALL USING (auth.uid() = user_id);

-- coin_balance: users can only read their own balance
CREATE POLICY "Own balance only" ON coin_balance
  FOR ALL USING (auth.uid() = user_id);

-- coin_transactions: users can only read their own transactions
CREATE POLICY "Own transactions only" ON coin_transactions
  FOR ALL USING (auth.uid() = user_id);


-- ============================================================
-- Storage bucket: cv-pdfs
-- ============================================================
-- Run this separately in Supabase Dashboard → Storage (create bucket manually)
-- OR via SQL:
-- INSERT INTO storage.buckets (id, name, public) VALUES ('cv-pdfs', 'cv-pdfs', true)
--   ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- Auto-update updated_at triggers
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cv_profiles_updated_at    ON cv_profiles;
DROP TRIGGER IF EXISTS trg_cv_sessions_updated_at    ON cv_sessions;
DROP TRIGGER IF EXISTS trg_user_settings_updated_at  ON user_settings;
DROP TRIGGER IF EXISTS trg_coin_balance_updated_at   ON coin_balance;

CREATE TRIGGER trg_cv_profiles_updated_at
  BEFORE UPDATE ON cv_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_cv_sessions_updated_at
  BEFORE UPDATE ON cv_sessions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_user_settings_updated_at
  BEFORE UPDATE ON user_settings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_coin_balance_updated_at
  BEFORE UPDATE ON coin_balance
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
