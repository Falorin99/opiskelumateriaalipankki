-- Allowed classifications are stored in SQLite, not hard-coded in the form.
INSERT OR IGNORE INTO subjects (name) VALUES ('Ohjelmointi');
INSERT OR IGNORE INTO subjects (name) VALUES ('Algoritmit');
INSERT OR IGNORE INTO subjects (name) VALUES ('Tietokannat');
INSERT OR IGNORE INTO subjects (name) VALUES ('Matematiikka');
INSERT OR IGNORE INTO subjects (name) VALUES ('Tekoäly');
INSERT OR IGNORE INTO subjects (name) VALUES ('Muu');

INSERT OR IGNORE INTO material_types (name) VALUES ('Video');
INSERT OR IGNORE INTO material_types (name) VALUES ('Artikkeli');
INSERT OR IGNORE INTO material_types (name) VALUES ('Kirja');
INSERT OR IGNORE INTO material_types (name) VALUES ('Verkkokurssi');
INSERT OR IGNORE INTO material_types (name) VALUES ('Opas');
