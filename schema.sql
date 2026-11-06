CREATE DATABASE IF NOT EXISTS course_analytics
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE course_analytics;

CREATE TABLE IF NOT EXISTS students (
  student_id INT NOT NULL AUTO_INCREMENT,
  student_name VARCHAR(120) NOT NULL,
  age TINYINT UNSIGNED NOT NULL,
  registration_number VARCHAR(64) NOT NULL,
  section VARCHAR(50) NOT NULL,
  study_year TINYINT UNSIGNED NOT NULL,
  department VARCHAR(120) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (student_id),
  UNIQUE KEY uq_students_registration_number (registration_number)
);

CREATE TABLE IF NOT EXISTS courses (
  course_id INT NOT NULL AUTO_INCREMENT,
  course_name VARCHAR(200) NOT NULL,
  category VARCHAR(100),
  PRIMARY KEY (course_id)
);

CREATE TABLE IF NOT EXISTS learners (
  learner_id INT NOT NULL AUTO_INCREMENT,
  roll_no VARCHAR(50) NULL,
  PRIMARY KEY (learner_id),
  UNIQUE KEY uq_learners_roll_no (roll_no)
);

CREATE TABLE IF NOT EXISTS enrollments (
  enrollment_id INT NOT NULL AUTO_INCREMENT,
  learner_id INT NOT NULL,
  course_id INT NOT NULL,
  enrolled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status ENUM('active', 'completed', 'withdrawn') NOT NULL DEFAULT 'active',
  PRIMARY KEY (enrollment_id),
  KEY ix_enrollments_course_status (course_id, status),
  KEY ix_enrollments_learner (learner_id),
  CONSTRAINT fk_enrollments_learner
    FOREIGN KEY (learner_id) REFERENCES learners (learner_id),
  CONSTRAINT fk_enrollments_course
    FOREIGN KEY (course_id) REFERENCES courses (course_id)
);

CREATE TABLE IF NOT EXISTS activities (
  activity_id BIGINT NOT NULL AUTO_INCREMENT,
  enrollment_id INT NOT NULL,
  activity_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  activity_type VARCHAR(100) NOT NULL,
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (activity_id),
  KEY ix_activities_enrollment_date (enrollment_id, activity_date),
  CONSTRAINT fk_activities_enrollment
    FOREIGN KEY (enrollment_id) REFERENCES enrollments (enrollment_id)
);