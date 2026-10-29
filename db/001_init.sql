-- Solar plant enterprise work orders. Idempotent even on persistent DB01 volumes.
CREATE TABLE IF NOT EXISTS work_orders (
 id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('planned','approved','closed')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO work_orders(reference,title,status) VALUES
('WO-PV-1001','Thermal inspection — PV combiner block PV-01','planned'),
('WO-PV-1002','Review inverter INV-02 DC insulation test','approved'),
('WO-PV-1003','Verify 33 kV feeder relay trip event logs','planned'),
('WO-PV-1004','PPC active-power dispatch acceptance test','approved'),
('WO-PV-1005','Validate MET-01 pyranometer calibration','planned')
ON CONFLICT(reference) DO UPDATE SET title=excluded.title;

-- Immutable approval/closure audit trail; migration script applies this on reused volumes.
CREATE TABLE IF NOT EXISTS work_order_events (
 id BIGSERIAL PRIMARY KEY,
 reference TEXT NOT NULL,
 actor TEXT NOT NULL,
 old_status TEXT NOT NULL,
 new_status TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '',
 changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
