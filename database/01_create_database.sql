-- =====================================================================================
-- 1K Saver Club: step 1 of 2: create the database and the application user
-- Works on MySQL 8.0+ and MariaDB 10.4+ (XAMPP).  Run as a privileged user (root):
--     mysql -u root -p < database/01_create_database.sql
-- BEFORE RUNNING: replace CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD (twice-check it matches DB_PASSWORD in .env).
-- =====================================================================================

-- utf8mb4 so names, UGX/emoji (offer categories use emoji) and every language store correctly.
-- utf8mb4_unicode_ci is used (not the MySQL-8-only 0900_ai_ci) so the same script also works on MariaDB.
CREATE DATABASE IF NOT EXISTS `savings_hub`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- The app connects as this user. 'localhost' = same machine. For Docker / a separate DB server use '%'
-- (or the app server's IP) instead of 'localhost'.
CREATE USER IF NOT EXISTS 'savings_hub_user'@'localhost' IDENTIFIED BY 'CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD';

-- Least privilege: full control of THIS database only (Django migrations need CREATE/ALTER/DROP/INDEX/REFERENCES),
-- no access to any other database, no FILE / SUPER / PROCESS / GRANT.
GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, ALTER, DROP, INDEX, REFERENCES,
      CREATE TEMPORARY TABLES, LOCK TABLES
   ON `savings_hub`.* TO 'savings_hub_user'@'localhost';

-- Only needed on a developer machine to run `manage.py test` (Django creates/destroys a `test_savings_hub` database).
-- Delete these two lines on a production server.
GRANT ALL PRIVILEGES ON `test\_savings\_hub`.* TO 'savings_hub_user'@'localhost';

FLUSH PRIVILEGES;
