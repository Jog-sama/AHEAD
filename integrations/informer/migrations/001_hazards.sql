CREATE TABLE IF NOT EXISTS hazards (
  event_id UUID PRIMARY KEY,
  observed_at TIMESTAMPTZ NOT NULL,
  label TEXT NOT NULL,
  simulated BOOLEAN NOT NULL,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hazards_observed ON hazards(observed_at DESC);
