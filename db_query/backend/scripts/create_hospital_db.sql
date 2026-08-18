-- ============================================================
-- 医院职工数据库建库建表脚本
-- 用法: mysql -u root -h localhost -P 3306 < create_hospital_db.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS hospital_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE hospital_db;

DROP TABLE IF EXISTS staff;
DROP TABLE IF EXISTS departments;

-- 科室表
CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '科室ID',
    name VARCHAR(50) NOT NULL COMMENT '科室名称',
    location VARCHAR(100) DEFAULT NULL COMMENT '科室位置',
    phone VARCHAR(20) DEFAULT NULL COMMENT '科室电话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_department_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='科室表';

-- 职工表
CREATE TABLE staff (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '职工ID',
    employee_no VARCHAR(20) NOT NULL COMMENT '工号',
    name VARCHAR(50) NOT NULL COMMENT '职工姓名',
    gender ENUM('男', '女') NOT NULL COMMENT '性别',
    age INT DEFAULT NULL COMMENT '年龄',
    position VARCHAR(50) NOT NULL COMMENT '职位(职务)',
    title VARCHAR(50) DEFAULT NULL COMMENT '职称(可为空, 行政/后勤人员通常无职称)',
    department_id INT NOT NULL COMMENT '所属科室ID',
    hire_date DATE DEFAULT NULL COMMENT '入职日期',
    phone VARCHAR(20) DEFAULT NULL COMMENT '联系电话',
    salary DECIMAL(10, 2) DEFAULT NULL COMMENT '月薪(元)',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否在职: 1在职 0离职',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    UNIQUE KEY uk_employee_no (employee_no),
    KEY idx_department (department_id),
    KEY idx_name (name),
    CONSTRAINT fk_staff_department FOREIGN KEY (department_id) REFERENCES departments (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='医院职工表';
