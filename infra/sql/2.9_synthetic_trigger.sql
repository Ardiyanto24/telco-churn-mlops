-- Milestone 2.9 -- trigger event-driven: synthetic_generation_runs selesai
-- (status='completed') memicu GitHub repository_dispatch lewat ekstensi
-- pg_net, yang menjalankan workflow .github/workflows/synthetic-auto-scoring.yml.
-- Lihat milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md
-- Keputusan #1 dan #4.
--
-- PRASYARAT sebelum file ini dijalankan: secret 'github_repository_dispatch_pat'
-- SUDAH tersimpan di Supabase Vault (vault.create_secret(...), dijalankan
-- terpisah dengan nilai PAT asli -- TIDAK pernah di-commit ke file ini).

CREATE EXTENSION IF NOT EXISTS pg_net;

CREATE OR REPLACE FUNCTION public.notify_synthetic_generation_completed()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault, net
AS $$
DECLARE
  gh_pat text;
  request_id bigint;
BEGIN
  -- Guard: hanya fire saat status BENAR-BENAR baru jadi 'completed' --
  -- INSERT langsung dengan status='completed' (pola generator ini, lihat
  -- logs.md) selalu fire; UPDATE hanya fire kalau status BERUBAH ke
  -- 'completed' (bukan update lain pada baris yang sudah completed).
  IF NEW.status <> 'completed' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.status IS NOT DISTINCT FROM NEW.status THEN
    RETURN NEW;
  END IF;

  SELECT decrypted_secret INTO gh_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_repository_dispatch_pat';

  IF gh_pat IS NULL THEN
    RAISE WARNING 'notify_synthetic_generation_completed: secret github_repository_dispatch_pat tidak ditemukan di vault -- dispatch DILEWATI, generation_id=%', NEW.generation_id;
    RETURN NEW;
  END IF;

  SELECT net.http_post(
    url := 'https://api.github.com/repos/Ardiyanto24/telco-churn-mlops/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || gh_pat,
      'Accept', 'application/vnd.github+json',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object(
      'event_type', 'synthetic-data-arrived',
      'client_payload', jsonb_build_object(
        'generation_id', NEW.generation_id,
        'inserted_count', NEW.inserted_count
      )
    ),
    timeout_milliseconds := 5000
  ) INTO request_id;

  RAISE LOG 'notify_synthetic_generation_completed: dispatch terkirim, generation_id=%, net_request_id=%', NEW.generation_id, request_id;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_synthetic_generation_completed ON public.synthetic_generation_runs;

CREATE TRIGGER trg_notify_synthetic_generation_completed
AFTER INSERT OR UPDATE ON public.synthetic_generation_runs
FOR EACH ROW
WHEN (NEW.status = 'completed')
EXECUTE FUNCTION public.notify_synthetic_generation_completed();

-- Verifikasi pengiriman: SELECT * FROM net._http_response ORDER BY created DESC LIMIT 5;
-- (async -- respons muncul beberapa detik setelah net.http_post dipanggil)
