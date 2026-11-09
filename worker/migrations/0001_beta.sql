-- One row per person who asked to join the beta. `status`: queued (waiting for App Store Connect), invited
-- (Apple has been asked to email the TestFlight invitation), no-lidar (the phone cannot run the app; no invitation
-- asked for), failed (App Store Connect refused; `error` holds its message, `POST /beta/flush` retries).
CREATE TABLE beta (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  email   TEXT NOT NULL UNIQUE COLLATE NOCASE,
  created INTEGER NOT NULL,
  device  TEXT NOT NULL,
  role    TEXT NOT NULL,
  status  TEXT NOT NULL,
  source  TEXT NOT NULL,
  error   TEXT
);
