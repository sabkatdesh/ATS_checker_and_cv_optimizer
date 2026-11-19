-- Private storage buckets. All buckets are private; the API signs short-lived URLs.
-- No policies are created on storage.objects for anon or authenticated: with RLS on and
-- no policy, clients cannot read, list or upload directly. Only the backend secret key
-- (which bypasses RLS) touches objects, after validation (and EXIF strip for photos).

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('photos',  'photos',  false, 10485760, array['image/jpeg', 'image/png', 'image/webp']),
  ('renders', 'renders', false, 10485760, array['application/pdf', 'image/webp', 'image/png']),
  ('imports', 'imports', false, 10485760, array['application/pdf']),
  ('exports', 'exports', false, 10485760, array['application/zip'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;
