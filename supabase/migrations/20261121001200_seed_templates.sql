-- Interim seed of the six built-in templates; replaced from manifests later.
insert into public.templates
  (id, version, name, description, tier, ats_safe, recommended_domains, manifest, is_active)
values
  ('classic', 1, 'Classic', 'Clean two-column layout. ATS-safe, widely accepted.', 'standard', true, array['general','finance','legal','education'], '{}', true),
  ('modern', 1, 'Modern', 'Bold header, accent sidebar. Professional and eye-catching.', 'standard', false, array['tech','creative','marketing'], '{}', true),
  ('compact', 1, 'Compact', 'Dense single-page layout for experienced professionals.', 'standard', true, array['general','tech','finance'], '{}', true),
  ('academic', 1, 'Academic', 'Publications, research, and citations front and center.', 'standard', true, array['education','research','medical'], '{}', true),
  ('trades', 1, 'Trades', 'Certifications, licenses, and site experience highlighted.', 'standard', true, array['trades','engineering','construction'], '{}', true),
  ('creative', 1, 'Creative', 'Portfolio-ready. Full-bleed accents, project showcase.', 'standard', false, array['creative','design','media'], '{}', true)
on conflict (id) do update set
  version = excluded.version,
  name = excluded.name,
  description = excluded.description,
  tier = excluded.tier,
  ats_safe = excluded.ats_safe,
  recommended_domains = excluded.recommended_domains,
  manifest = excluded.manifest,
  is_active = excluded.is_active;
