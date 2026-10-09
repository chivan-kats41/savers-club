-- =====================================================================================
-- 1K Saver Club: step 2 of 2: database schema (63 tables, InnoDB, utf8mb4)
-- Generated from the Django models by migrating a real MySQL 8.0 server, then dumping it. Do not edit by hand:
-- change the models, run `manage.py makemigrations`, and regenerate (see database/README.md).
--
-- Load into the (empty) database created by 01_create_database.sql:
--     mysql -u savings_hub_user -p savings_hub < database/02_schema.sql
-- Then load 03_reference_data.sql, then run `python manage.py migrate` (see README: it applies nothing, it just
-- creates Django's permission rows). Safe to re-run: every table is CREATE TABLE IF NOT EXISTS.
-- Works on MySQL 8.0+ and MariaDB 10.5+ (Django 6.1 itself needs MySQL 8.4+ / MariaDB 10.11+).
-- =====================================================================================


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_emailverification` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `token` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_used` tinyint(1) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`),
  KEY `accounts_emailverification_user_id_4f5b1661_fk_accounts_user_id` (`user_id`),
  CONSTRAINT `accounts_emailverification_user_id_4f5b1661_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_loginattempt` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `identifier` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ip_address` char(39) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `success` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `accounts_loginattempt_user_id_82a41308_fk_accounts_user_id` (`user_id`),
  KEY `accounts_loginattempt_identifier_e5dbba39` (`identifier`),
  KEY `accounts_lo_identif_19f84b_idx` (`identifier`,`created_at`),
  CONSTRAINT `accounts_loginattempt_user_id_82a41308_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_phoneverification` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `purpose` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `attempts` smallint unsigned NOT NULL,
  `max_attempts` smallint unsigned NOT NULL,
  `is_used` tinyint(1) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `accounts_ph_user_id_0c0b77_idx` (`user_id`,`purpose`,`is_used`),
  CONSTRAINT `accounts_phoneverification_user_id_2b159574_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `accounts_phoneverification_chk_1` CHECK ((`attempts` >= 0)),
  CONSTRAINT `accounts_phoneverification_chk_2` CHECK ((`max_attempts` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_securityevent` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ip_address` char(39) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata` json NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `accounts_se_user_id_a2587d_idx` (`user_id`,`event_type`,`created_at`),
  CONSTRAINT `accounts_securityevent_user_id_b711491d_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_user` (
  `password` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(254) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `first_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `phone_verified` tinyint(1) NOT NULL,
  `email_verified` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_staff` tinyint(1) NOT NULL,
  `date_joined` datetime(6) NOT NULL,
  `totp_enabled` tinyint(1) NOT NULL,
  `totp_secret` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `phone` (`phone`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_user_groups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `group_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `accounts_user_groups_user_id_group_id_59c0b32f_uniq` (`user_id`,`group_id`),
  KEY `accounts_user_groups_group_id_bd11a704_fk_auth_group_id` (`group_id`),
  CONSTRAINT `accounts_user_groups_group_id_bd11a704_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`),
  CONSTRAINT `accounts_user_groups_user_id_52b62117_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_user_user_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `accounts_user_user_permi_user_id_permission_id_2ab516c2_uniq` (`user_id`,`permission_id`),
  KEY `accounts_user_user_p_permission_id_113bb443_fk_auth_perm` (`permission_id`),
  CONSTRAINT `accounts_user_user_p_permission_id_113bb443_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `accounts_user_user_p_user_id_e4f0a161_fk_accounts_` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `accounts_userrole` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `role` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `assigned_at` datetime(6) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `accounts_userrole_user_id_role_ab744f91_uniq` (`user_id`,`role`),
  CONSTRAINT `accounts_userrole_user_id_eba3c754_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `agents_agent` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  CONSTRAINT `agents_agent_user_id_98b0ac68_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `agents_agent_areas` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `agent_id` bigint NOT NULL,
  `area_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `agents_agent_areas_agent_id_area_id_9bc839de_uniq` (`agent_id`,`area_id`),
  KEY `agents_agent_areas_area_id_375c93e3_fk_core_area_id` (`area_id`),
  CONSTRAINT `agents_agent_areas_agent_id_b9679a81_fk_agents_agent_id` FOREIGN KEY (`agent_id`) REFERENCES `agents_agent` (`id`),
  CONSTRAINT `agents_agent_areas_area_id_375c93e3_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `agents_agentearning` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `source` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `reference` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `agent_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `agents_agentearning_agent_id_a8aaca53_fk_agents_agent_id` (`agent_id`),
  CONSTRAINT `agents_agentearning_agent_id_a8aaca53_fk_agents_agent_id` FOREIGN KEY (`agent_id`) REFERENCES `agents_agent` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `agents_agenttask` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `kind` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `due_at` datetime(6) DEFAULT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `agent_id` bigint NOT NULL,
  `area_id` bigint DEFAULT NULL,
  `created_by_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `agents_agenttask_agent_id_70ebf28c_fk_agents_agent_id` (`agent_id`),
  KEY `agents_agenttask_area_id_c875dd48_fk_core_area_id` (`area_id`),
  KEY `agents_agenttask_created_by_id_ffdc39d9_fk_accounts_user_id` (`created_by_id`),
  CONSTRAINT `agents_agenttask_agent_id_70ebf28c_fk_agents_agent_id` FOREIGN KEY (`agent_id`) REFERENCES `agents_agent` (`id`),
  CONSTRAINT `agents_agenttask_area_id_c875dd48_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `agents_agenttask_created_by_id_ffdc39d9_fk_accounts_user_id` FOREIGN KEY (`created_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `agents_pricerecord` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `item_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `price` decimal(12,2) NOT NULL,
  `agent_id` bigint NOT NULL,
  `area_id` bigint NOT NULL,
  `category_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `agents_pricerecord_agent_id_11bc4c45_fk_agents_agent_id` (`agent_id`),
  KEY `agents_pricerecord_category_id_6b4a750f_fk_offers_of` (`category_id`),
  KEY `agents_pric_area_id_bbc888_idx` (`area_id`,`category_id`,`created_at`),
  CONSTRAINT `agents_pricerecord_agent_id_11bc4c45_fk_agents_agent_id` FOREIGN KEY (`agent_id`) REFERENCES `agents_agent` (`id`),
  CONSTRAINT `agents_pricerecord_area_id_d15feaf3_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `agents_pricerecord_category_id_6b4a750f_fk_offers_of` FOREIGN KEY (`category_id`) REFERENCES `offers_offercategory` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `auth_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `auth_group_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `auth_permission` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type_id` int NOT NULL,
  `codename` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`),
  CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `claims_claimevent` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `event_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata` json NOT NULL,
  `actor_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claim_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `claims_claimevent_actor_id_7e5ae3c9_fk_accounts_user_id` (`actor_id`),
  KEY `claims_claimevent_claim_id_2de4ec01_fk_claims_offerclaim_id` (`claim_id`),
  CONSTRAINT `claims_claimevent_actor_id_7e5ae3c9_fk_accounts_user_id` FOREIGN KEY (`actor_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `claims_claimevent_claim_id_2de4ec01_fk_claims_offerclaim_id` FOREIGN KEY (`claim_id`) REFERENCES `claims_offerclaim` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `claims_offerclaim` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_saving` decimal(12,2) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `redeemed_at` datetime(6) DEFAULT NULL,
  `redemption_attempts` smallint unsigned NOT NULL,
  `member_id` bigint NOT NULL,
  `offer_id` bigint NOT NULL,
  `redeemed_by_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `claims_offe_status_20ad47_idx` (`status`,`expires_at`),
  KEY `claims_offe_member__ea93d7_idx` (`member_id`,`status`),
  KEY `claims_offerclaim_offer_id_697d2cb0_fk_offers_offer_id` (`offer_id`),
  KEY `claims_offerclaim_redeemed_by_id_cdcd4b6e_fk_accounts_user_id` (`redeemed_by_id`),
  CONSTRAINT `claims_offerclaim_member_id_138ee4d1_fk_members_member_id` FOREIGN KEY (`member_id`) REFERENCES `members_member` (`id`),
  CONSTRAINT `claims_offerclaim_offer_id_697d2cb0_fk_offers_offer_id` FOREIGN KEY (`offer_id`) REFERENCES `offers_offer` (`id`),
  CONSTRAINT `claims_offerclaim_redeemed_by_id_cdcd4b6e_fk_accounts_user_id` FOREIGN KEY (`redeemed_by_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `claims_offerclaim_chk_1` CHECK ((`redemption_attempts` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `complaints_complaint` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `subject` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `area_id` bigint NOT NULL,
  `assigned_agent_id` bigint DEFAULT NULL,
  `member_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `complaints__area_id_62b95f_idx` (`area_id`,`status`),
  KEY `complaints__assigne_4f7ae1_idx` (`assigned_agent_id`,`status`),
  KEY `complaints_complaint_member_id_86d3aac7_fk_members_member_id` (`member_id`),
  CONSTRAINT `complaints_complaint_area_id_a0673580_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `complaints_complaint_assigned_agent_id_15d7d6b6_fk_agents_ag` FOREIGN KEY (`assigned_agent_id`) REFERENCES `agents_agent` (`id`),
  CONSTRAINT `complaints_complaint_member_id_86d3aac7_fk_members_member_id` FOREIGN KEY (`member_id`) REFERENCES `members_member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `complaints_complaintmessage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `message` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `complaint_id` bigint NOT NULL,
  `sender_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `complaints_complaint_complaint_id_0255aa32_fk_complaint` (`complaint_id`),
  KEY `complaints_complaint_sender_id_6d6c7b30_fk_accounts_` (`sender_id`),
  CONSTRAINT `complaints_complaint_complaint_id_0255aa32_fk_complaint` FOREIGN KEY (`complaint_id`) REFERENCES `complaints_complaint` (`id`),
  CONSTRAINT `complaints_complaint_sender_id_6d6c7b30_fk_accounts_` FOREIGN KEY (`sender_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `complaints_complaintresolution` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `resolution_note` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `complaint_id` bigint NOT NULL,
  `resolved_by_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `complaint_id` (`complaint_id`),
  KEY `complaints_complaint_resolved_by_id_ef1f9827_fk_accounts_` (`resolved_by_id`),
  CONSTRAINT `complaints_complaint_complaint_id_b828c21c_fk_complaint` FOREIGN KEY (`complaint_id`) REFERENCES `complaints_complaint` (`id`),
  CONSTRAINT `complaints_complaint_resolved_by_id_ef1f9827_fk_accounts_` FOREIGN KEY (`resolved_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `core_area` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_launch_area` tinyint(1) NOT NULL,
  `latitude` decimal(9,6) DEFAULT NULL,
  `longitude` decimal(9,6) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `core_auditlog` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `action` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `object_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `object_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ip_address` char(39) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata` json NOT NULL,
  `actor_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `core_auditl_actor_i_41600a_idx` (`actor_id`,`created_at`),
  KEY `core_auditl_action_29a2bf_idx` (`action`,`created_at`),
  KEY `core_auditl_object__42e4a9_idx` (`object_type`,`object_id`),
  CONSTRAINT `core_auditlog_actor_id_ab091f3c_fk_accounts_user_id` FOREIGN KEY (`actor_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `core_riskevent` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `event_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ip_address` char(39) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metadata` json NOT NULL,
  `reviewed` tinyint(1) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `core_riskev_user_id_ea04bf_idx` (`user_id`,`event_type`,`created_at`),
  CONSTRAINT `core_riskevent_user_id_f17e49f4_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `core_systemsetting` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `deliveries_deliveryjob` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `dropoff_address` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `delivery_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `fare` decimal(10,2) NOT NULL,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assigned_at` datetime(6) DEFAULT NULL,
  `picked_up_at` datetime(6) DEFAULT NULL,
  `delivered_at` datetime(6) DEFAULT NULL,
  `failed_at` datetime(6) DEFAULT NULL,
  `failure_reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `claim_id` bigint DEFAULT NULL,
  `dropoff_area_id` bigint NOT NULL,
  `pickup_merchant_id` bigint NOT NULL,
  `rider_id` bigint DEFAULT NULL,
  `route_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `claim_id` (`claim_id`),
  KEY `deliveries_deliveryjob_dropoff_area_id_d2e5c75d_fk_core_area_id` (`dropoff_area_id`),
  KEY `deliveries_deliveryj_pickup_merchant_id_35d7b3e8_fk_merchants` (`pickup_merchant_id`),
  KEY `deliveries__status_41efa8_idx` (`status`,`dropoff_area_id`),
  KEY `deliveries__rider_i_0a2307_idx` (`rider_id`,`status`),
  KEY `deliveries_deliveryj_route_id_9110e8a0_fk_deliverie` (`route_id`),
  CONSTRAINT `deliveries_deliveryj_pickup_merchant_id_35d7b3e8_fk_merchants` FOREIGN KEY (`pickup_merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `deliveries_deliveryj_route_id_9110e8a0_fk_deliverie` FOREIGN KEY (`route_id`) REFERENCES `deliveries_sharedroute` (`id`),
  CONSTRAINT `deliveries_deliveryjob_claim_id_d379b334_fk_claims_offerclaim_id` FOREIGN KEY (`claim_id`) REFERENCES `claims_offerclaim` (`id`),
  CONSTRAINT `deliveries_deliveryjob_dropoff_area_id_d2e5c75d_fk_core_area_id` FOREIGN KEY (`dropoff_area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `deliveries_deliveryjob_rider_id_7a55b56e_fk_riders_rider_id` FOREIGN KEY (`rider_id`) REFERENCES `riders_rider` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `deliveries_deliveryotp` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `code_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `attempts` smallint unsigned NOT NULL,
  `max_attempts` smallint unsigned NOT NULL,
  `is_used` tinyint(1) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `job_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `job_id` (`job_id`),
  CONSTRAINT `deliveries_deliveryo_job_id_a133dd30_fk_deliverie` FOREIGN KEY (`job_id`) REFERENCES `deliveries_deliveryjob` (`id`),
  CONSTRAINT `deliveries_deliveryotp_chk_1` CHECK ((`attempts` >= 0)),
  CONSTRAINT `deliveries_deliveryotp_chk_2` CHECK ((`max_attempts` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `deliveries_deliverystatushistory` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `from_status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `to_status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `notes` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_by_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `job_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `deliveries_deliverys_changed_by_id_7c4db4bc_fk_accounts_` (`changed_by_id`),
  KEY `deliveries_deliverys_job_id_6a4d1e36_fk_deliverie` (`job_id`),
  CONSTRAINT `deliveries_deliverys_changed_by_id_7c4db4bc_fk_accounts_` FOREIGN KEY (`changed_by_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `deliveries_deliverys_job_id_6a4d1e36_fk_deliverie` FOREIGN KEY (`job_id`) REFERENCES `deliveries_deliveryjob` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `deliveries_pickuppoint` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `address` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contact_phone` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `opening_hours` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `area_id` bigint NOT NULL,
  `created_by_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `deliveries_pickuppoint_area_id_c874bda0_fk_core_area_id` (`area_id`),
  KEY `deliveries_pickuppoi_created_by_id_00178e24_fk_accounts_` (`created_by_id`),
  CONSTRAINT `deliveries_pickuppoi_created_by_id_00178e24_fk_accounts_` FOREIGN KEY (`created_by_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `deliveries_pickuppoint_area_id_c874bda0_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `deliveries_riderearning` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `gross_amount` decimal(10,2) NOT NULL,
  `commission_amount` decimal(10,2) NOT NULL,
  `net_amount` decimal(10,2) NOT NULL,
  `delivery_job_id` bigint NOT NULL,
  `rider_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `delivery_job_id` (`delivery_job_id`),
  KEY `deliveries_riderearning_rider_id_c710695a_fk_riders_rider_id` (`rider_id`),
  CONSTRAINT `deliveries_riderearn_delivery_job_id_726992a6_fk_deliverie` FOREIGN KEY (`delivery_job_id`) REFERENCES `deliveries_deliveryjob` (`id`),
  CONSTRAINT `deliveries_riderearning_rider_id_c710695a_fk_riders_rider_id` FOREIGN KEY (`rider_id`) REFERENCES `riders_rider` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `deliveries_sharedroute` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `departure_time` datetime(6) NOT NULL,
  `max_packages` smallint unsigned NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `destination_area_id` bigint NOT NULL,
  `origin_area_id` bigint NOT NULL,
  `rider_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `deliveries__status_4ac163_idx` (`status`,`origin_area_id`,`destination_area_id`),
  KEY `deliveries_sharedrou_destination_area_id_65c4e091_fk_core_area` (`destination_area_id`),
  KEY `deliveries_sharedroute_origin_area_id_c9165d91_fk_core_area_id` (`origin_area_id`),
  KEY `deliveries_sharedroute_rider_id_857db4a2_fk_riders_rider_id` (`rider_id`),
  CONSTRAINT `deliveries_sharedrou_destination_area_id_65c4e091_fk_core_area` FOREIGN KEY (`destination_area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `deliveries_sharedroute_origin_area_id_c9165d91_fk_core_area_id` FOREIGN KEY (`origin_area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `deliveries_sharedroute_rider_id_857db4a2_fk_riders_rider_id` FOREIGN KEY (`rider_id`) REFERENCES `riders_rider` (`id`),
  CONSTRAINT `deliveries_sharedroute_chk_1` CHECK ((`max_packages` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `django_admin_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext COLLATE utf8mb4_unicode_ci,
  `object_repr` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_flag` smallint unsigned NOT NULL,
  `change_message` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type_id` int DEFAULT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  KEY `django_admin_log_user_id_c564eba6_fk_accounts_user_id` (`user_id`),
  CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  CONSTRAINT `django_admin_log_user_id_c564eba6_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `django_admin_log_chk_1` CHECK ((`action_flag` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `django_content_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `model` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `django_migrations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `app` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `django_session` (
  `session_key` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_data` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_a5c62663` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `item_requests_memberrequest` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `item_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `max_budget` decimal(12,2) DEFAULT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `area_id` bigint NOT NULL,
  `member_id` bigint NOT NULL,
  `fulfilled_response_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `item_requests_member_fulfilled_response_i_2f8d8f62_fk_item_requ` (`fulfilled_response_id`),
  KEY `item_reques_area_id_30a29b_idx` (`area_id`,`status`),
  KEY `item_reques_member__7e9671_idx` (`member_id`,`status`),
  CONSTRAINT `item_requests_member_fulfilled_response_i_2f8d8f62_fk_item_requ` FOREIGN KEY (`fulfilled_response_id`) REFERENCES `item_requests_requestresponse` (`id`),
  CONSTRAINT `item_requests_member_member_id_c9ec7dbf_fk_members_m` FOREIGN KEY (`member_id`) REFERENCES `members_member` (`id`),
  CONSTRAINT `item_requests_memberrequest_area_id_2a9dfea4_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `item_requests_requestresponse` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `message` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `price` decimal(12,2) DEFAULT NULL,
  `merchant_id` bigint NOT NULL,
  `request_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `item_requests_requestres_request_id_merchant_id_169cee5c_uniq` (`request_id`,`merchant_id`),
  KEY `item_requests_reques_merchant_id_8b821963_fk_merchants` (`merchant_id`),
  CONSTRAINT `item_requests_reques_merchant_id_8b821963_fk_merchants` FOREIGN KEY (`merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `item_requests_reques_request_id_e352f61b_fk_item_requ` FOREIGN KEY (`request_id`) REFERENCES `item_requests_memberrequest` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `members_member` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `account_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `referral_code` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `area_id` bigint NOT NULL,
  `referred_by_id` bigint DEFAULT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `referral_code` (`referral_code`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `members_member_area_id_8c544b26_fk_core_area_id` (`area_id`),
  KEY `members_member_referred_by_id_17ca75b5_fk_members_member_id` (`referred_by_id`),
  CONSTRAINT `members_member_area_id_8c544b26_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `members_member_referred_by_id_17ca75b5_fk_members_member_id` FOREIGN KEY (`referred_by_id`) REFERENCES `members_member` (`id`),
  CONSTRAINT `members_member_user_id_5b73e2f8_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `members_referralreward` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `credited_at` datetime(6) DEFAULT NULL,
  `referred_member_id` bigint NOT NULL,
  `referrer_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `referred_member_id` (`referred_member_id`),
  KEY `members_referralreward_referrer_id_57c03d22_fk_members_member_id` (`referrer_id`),
  CONSTRAINT `members_referralrewa_referred_member_id_f2d72831_fk_members_m` FOREIGN KEY (`referred_member_id`) REFERENCES `members_member` (`id`),
  CONSTRAINT `members_referralreward_referrer_id_57c03d22_fk_members_member_id` FOREIGN KEY (`referrer_id`) REFERENCES `members_member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `merchants_merchant` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `business_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `vendor_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `address` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `latitude` decimal(9,6) DEFAULT NULL,
  `longitude` decimal(9,6) DEFAULT NULL,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `whatsapp` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `verified_at` datetime(6) DEFAULT NULL,
  `area_id` bigint NOT NULL,
  `category_id` bigint NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `verified_by_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `merchants_merchant_category_id_b0660ca9_fk_offers_of` (`category_id`),
  KEY `merchants_merchant_verified_by_id_29015f65_fk_accounts_user_id` (`verified_by_id`),
  KEY `merchants_m_area_id_61d41b_idx` (`area_id`,`status`),
  CONSTRAINT `merchants_merchant_area_id_3aa553c8_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `merchants_merchant_category_id_b0660ca9_fk_offers_of` FOREIGN KEY (`category_id`) REFERENCES `offers_offercategory` (`id`),
  CONSTRAINT `merchants_merchant_user_id_574aeeef_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `merchants_merchant_verified_by_id_29015f65_fk_accounts_user_id` FOREIGN KEY (`verified_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `merchants_merchantdocument` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `doc_type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `merchant_id` bigint NOT NULL,
  `uploaded_by_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `merchants_merchantdo_merchant_id_d68ddf75_fk_merchants` (`merchant_id`),
  KEY `merchants_merchantdo_uploaded_by_id_3ba5e499_fk_accounts_` (`uploaded_by_id`),
  CONSTRAINT `merchants_merchantdo_merchant_id_d68ddf75_fk_merchants` FOREIGN KEY (`merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `merchants_merchantdo_uploaded_by_id_3ba5e499_fk_accounts_` FOREIGN KEY (`uploaded_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `merchants_merchantverification` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `outcome` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `checklist` json NOT NULL,
  `notes` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `merchant_id` bigint NOT NULL,
  `performed_by_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `merchants_merchantve_merchant_id_62521c1b_fk_merchants` (`merchant_id`),
  KEY `merchants_merchantve_performed_by_id_ca512d41_fk_accounts_` (`performed_by_id`),
  CONSTRAINT `merchants_merchantve_merchant_id_62521c1b_fk_merchants` FOREIGN KEY (`merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `merchants_merchantve_performed_by_id_ca512d41_fk_accounts_` FOREIGN KEY (`performed_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `notifications_notification` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `category` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_read` tinyint(1) NOT NULL,
  `metadata` json NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `notificatio_user_id_8a7c6b_idx` (`user_id`,`is_read`,`created_at`),
  CONSTRAINT `notifications_notification_user_id_b5e8c0ff_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `notifications_notificationpreference` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `sms_enabled` tinyint(1) NOT NULL,
  `email_enabled` tinyint(1) NOT NULL,
  `in_app_enabled` tinyint(1) NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  CONSTRAINT `notifications_notifi_user_id_7cfb3d3a_fk_accounts_` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `offers_offer` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `item_name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `normal_price` decimal(12,2) NOT NULL,
  `member_price` decimal(12,2) NOT NULL,
  `quantity` int unsigned NOT NULL,
  `pickup_location` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `delivery_available` tinyint(1) NOT NULL,
  `offer_radius_km` decimal(5,2) DEFAULT NULL,
  `packaging_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `visibility_score` int unsigned NOT NULL,
  `views_count` int unsigned NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `area_id` bigint NOT NULL,
  `merchant_id` bigint NOT NULL,
  `category_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `offers_offe_status_f98e70_idx` (`status`,`expires_at`),
  KEY `offers_offe_area_id_2998c1_idx` (`area_id`,`category_id`,`status`),
  KEY `offers_offer_merchant_id_26c339e1_fk_merchants_merchant_id` (`merchant_id`),
  KEY `offers_offer_category_id_bd5151d9_fk_offers_offercategory_id` (`category_id`),
  CONSTRAINT `offers_offer_area_id_efa7f630_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `offers_offer_category_id_bd5151d9_fk_offers_offercategory_id` FOREIGN KEY (`category_id`) REFERENCES `offers_offercategory` (`id`),
  CONSTRAINT `offers_offer_merchant_id_26c339e1_fk_merchants_merchant_id` FOREIGN KEY (`merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `offers_offer_chk_1` CHECK ((`quantity` >= 0)),
  CONSTRAINT `offers_offer_chk_2` CHECK ((`visibility_score` >= 0)),
  CONSTRAINT `offers_offer_chk_3` CHECK ((`views_count` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `offers_offercategory` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `key` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `label` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `emoji` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `offers_offerimage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `image` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_primary` tinyint(1) NOT NULL,
  `offer_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `offers_offerimage_offer_id_24ac23e8_fk_offers_offer_id` (`offer_id`),
  CONSTRAINT `offers_offerimage_offer_id_24ac23e8_fk_offers_offer_id` FOREIGN KEY (`offer_id`) REFERENCES `offers_offer` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `offers_offerinteraction` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `kind` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `offer_id` bigint NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `offers_offe_offer_i_200e04_idx` (`offer_id`,`kind`,`created_at`),
  KEY `offers_offerinteraction_user_id_5bfe232f_fk_accounts_user_id` (`user_id`),
  CONSTRAINT `offers_offerinteraction_offer_id_26aa1ca9_fk_offers_offer_id` FOREIGN KEY (`offer_id`) REFERENCES `offers_offer` (`id`),
  CONSTRAINT `offers_offerinteraction_user_id_5bfe232f_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `payments_ledgerentry` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `direction` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `fee` decimal(12,2) NOT NULL,
  `net_amount` decimal(12,2) NOT NULL,
  `reference` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payment_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `payments_le_user_id_38c09d_idx` (`user_id`,`created_at`),
  KEY `payments_ledgerentry_payment_id_b7e873cd_fk_payments_payment_id` (`payment_id`),
  CONSTRAINT `payments_ledgerentry_payment_id_b7e873cd_fk_payments_payment_id` FOREIGN KEY (`payment_id`) REFERENCES `payments_payment` (`id`),
  CONSTRAINT `payments_ledgerentry_user_id_374df45f_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `payments_payment` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `purpose` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `method` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `currency` varchar(3) COLLATE utf8mb4_unicode_ci NOT NULL,
  `internal_reference` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_transaction_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payer_phone` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payer_email` varchar(254) COLLATE utf8mb4_unicode_ci NOT NULL,
  `redirect_url` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subscription_payment_id` bigint DEFAULT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `promotion_purchase_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `internal_reference` (`internal_reference`),
  UNIQUE KEY `subscription_payment_id` (`subscription_payment_id`),
  UNIQUE KEY `promotion_purchase_id` (`promotion_purchase_id`),
  KEY `payments_pa_status_343680_idx` (`status`,`created_at`),
  KEY `payments_pa_user_id_01767a_idx` (`user_id`,`status`),
  CONSTRAINT `payments_payment_promotion_purchase_i_d68b704d_fk_promotion` FOREIGN KEY (`promotion_purchase_id`) REFERENCES `promotions_promotionpurchase` (`id`),
  CONSTRAINT `payments_payment_subscription_payment_e2cf08ba_fk_subscript` FOREIGN KEY (`subscription_payment_id`) REFERENCES `subscriptions_subscriptionpayment` (`id`),
  CONSTRAINT `payments_payment_user_id_f9db060a_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `payments_paymentcallback` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `raw_payload` json NOT NULL,
  `provider_status` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `processed` tinyint(1) NOT NULL,
  `processing_notes` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payment_id` bigint DEFAULT NULL,
  `provider_transaction_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `payments_pa_payment_4babaf_idx` (`payment_id`,`provider_status`,`provider_transaction_id`),
  CONSTRAINT `payments_paymentcall_payment_id_97e36d03_fk_payments_` FOREIGN KEY (`payment_id`) REFERENCES `payments_payment` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `payments_withdrawal` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `source` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `fee` decimal(12,2) NOT NULL,
  `net_amount` decimal(12,2) NOT NULL,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `internal_reference` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_transaction_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `internal_reference` (`internal_reference`),
  KEY `payments_wi_user_id_8ab084_idx` (`user_id`,`status`),
  KEY `payments_wi_status_eb5158_idx` (`status`,`created_at`),
  CONSTRAINT `payments_withdrawal_user_id_808b6c14_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `payments_withdrawalcallback` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `raw_payload` json NOT NULL,
  `provider_status` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_transaction_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `processed` tinyint(1) NOT NULL,
  `processing_notes` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `withdrawal_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `payments_withdrawalc_withdrawal_id_ed0764d9_fk_payments_` (`withdrawal_id`),
  CONSTRAINT `payments_withdrawalc_withdrawal_id_ed0764d9_fk_payments_` FOREIGN KEY (`withdrawal_id`) REFERENCES `payments_withdrawal` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `promotions_promotionpackage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `label` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `price` decimal(12,2) NOT NULL,
  `duration_days` int unsigned NOT NULL,
  `visibility_boost` int unsigned NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  CONSTRAINT `promotions_promotionpackage_chk_1` CHECK ((`duration_days` >= 0)),
  CONSTRAINT `promotions_promotionpackage_chk_2` CHECK ((`visibility_boost` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `promotions_promotionpurchase` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `starts_at` datetime(6) DEFAULT NULL,
  `expires_at` datetime(6) DEFAULT NULL,
  `merchant_id` bigint NOT NULL,
  `offer_id` bigint NOT NULL,
  `package_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `promotions_promotion_merchant_id_d730ae2c_fk_merchants` (`merchant_id`),
  KEY `promotions_promotion_offer_id_397e9110_fk_offers_of` (`offer_id`),
  KEY `promotions_promotion_package_id_3a96c92b_fk_promotion` (`package_id`),
  KEY `promotions__status_df7f4e_idx` (`status`,`expires_at`),
  CONSTRAINT `promotions_promotion_merchant_id_d730ae2c_fk_merchants` FOREIGN KEY (`merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `promotions_promotion_offer_id_397e9110_fk_offers_of` FOREIGN KEY (`offer_id`) REFERENCES `offers_offer` (`id`),
  CONSTRAINT `promotions_promotion_package_id_3a96c92b_fk_promotion` FOREIGN KEY (`package_id`) REFERENCES `promotions_promotionpackage` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `riders_rider` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `vehicle_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plate_number` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `verified_at` datetime(6) DEFAULT NULL,
  `is_available` tinyint(1) NOT NULL,
  `area_id` bigint NOT NULL,
  `user_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `verified_by_id` char(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `riders_ride_area_id_e054da_idx` (`area_id`,`status`,`is_available`),
  KEY `riders_rider_verified_by_id_8ef25a3f_fk_accounts_user_id` (`verified_by_id`),
  CONSTRAINT `riders_rider_area_id_888c172a_fk_core_area_id` FOREIGN KEY (`area_id`) REFERENCES `core_area` (`id`),
  CONSTRAINT `riders_rider_user_id_6f3e992e_fk_accounts_user_id` FOREIGN KEY (`user_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `riders_rider_verified_by_id_8ef25a3f_fk_accounts_user_id` FOREIGN KEY (`verified_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `riders_riderdocument` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `doc_type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `rider_id` bigint NOT NULL,
  `uploaded_by_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `riders_riderdocument_rider_id_62fe7218_fk_riders_rider_id` (`rider_id`),
  KEY `riders_riderdocument_uploaded_by_id_162a4a67_fk_accounts_user_id` (`uploaded_by_id`),
  CONSTRAINT `riders_riderdocument_rider_id_62fe7218_fk_riders_rider_id` FOREIGN KEY (`rider_id`) REFERENCES `riders_rider` (`id`),
  CONSTRAINT `riders_riderdocument_uploaded_by_id_162a4a67_fk_accounts_user_id` FOREIGN KEY (`uploaded_by_id`) REFERENCES `accounts_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `riders_riderverification` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `outcome` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `checklist` json NOT NULL,
  `notes` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `performed_by_id` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `rider_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `riders_riderverifica_performed_by_id_ef7fde8c_fk_accounts_` (`performed_by_id`),
  KEY `riders_riderverification_rider_id_ffc3745e_fk_riders_rider_id` (`rider_id`),
  CONSTRAINT `riders_riderverifica_performed_by_id_ef7fde8c_fk_accounts_` FOREIGN KEY (`performed_by_id`) REFERENCES `accounts_user` (`id`),
  CONSTRAINT `riders_riderverification_rider_id_ffc3745e_fk_riders_rider_id` FOREIGN KEY (`rider_id`) REFERENCES `riders_rider` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `savings_savingsrecord` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `normal_price` decimal(12,2) NOT NULL,
  `member_price` decimal(12,2) NOT NULL,
  `saving_amount` decimal(12,2) NOT NULL,
  `claim_id` bigint NOT NULL,
  `member_id` bigint NOT NULL,
  `merchant_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `claim_id` (`claim_id`),
  KEY `savings_savingsrecor_merchant_id_5b1ad678_fk_merchants` (`merchant_id`),
  KEY `savings_sav_member__fe4c73_idx` (`member_id`,`created_at`),
  CONSTRAINT `savings_savingsrecor_merchant_id_5b1ad678_fk_merchants` FOREIGN KEY (`merchant_id`) REFERENCES `merchants_merchant` (`id`),
  CONSTRAINT `savings_savingsrecord_claim_id_6586786a_fk_claims_offerclaim_id` FOREIGN KEY (`claim_id`) REFERENCES `claims_offerclaim` (`id`),
  CONSTRAINT `savings_savingsrecord_member_id_46a03676_fk_members_member_id` FOREIGN KEY (`member_id`) REFERENCES `members_member` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `subscriptions_subscription` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_period_start` datetime(6) DEFAULT NULL,
  `current_period_end` datetime(6) DEFAULT NULL,
  `auto_renew` tinyint(1) NOT NULL,
  `member_id` bigint NOT NULL,
  `plan_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `subscriptio_member__d3e8d6_idx` (`member_id`,`status`),
  KEY `subscriptions_subscr_plan_id_2c895107_fk_subscript` (`plan_id`),
  CONSTRAINT `subscriptions_subscr_member_id_2c9319b1_fk_members_m` FOREIGN KEY (`member_id`) REFERENCES `members_member` (`id`),
  CONSTRAINT `subscriptions_subscr_plan_id_2c895107_fk_subscript` FOREIGN KEY (`plan_id`) REFERENCES `subscriptions_subscriptionplan` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `subscriptions_subscriptionevent` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `event_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata` json NOT NULL,
  `subscription_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `subscriptions_subscr_subscription_id_6b1b4376_fk_subscript` (`subscription_id`),
  CONSTRAINT `subscriptions_subscr_subscription_id_6b1b4376_fk_subscript` FOREIGN KEY (`subscription_id`) REFERENCES `subscriptions_subscription` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `subscriptions_subscriptionpayment` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `external_reference` char(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_transaction_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subscription_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `external_reference` (`external_reference`),
  KEY `subscriptions_subscr_subscription_id_1fa490cf_fk_subscript` (`subscription_id`),
  CONSTRAINT `subscriptions_subscr_subscription_id_1fa490cf_fk_subscript` FOREIGN KEY (`subscription_id`) REFERENCES `subscriptions_subscription` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE IF NOT EXISTS `subscriptions_subscriptionplan` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `label` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `price` decimal(12,2) NOT NULL,
  `period_days` int unsigned NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_popular` tinyint(1) NOT NULL,
  `benefits` json NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  CONSTRAINT `subscriptions_subscriptionplan_chk_1` CHECK ((`period_days` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

