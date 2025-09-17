CREATE TABLE IF NOT EXISTS `kopilot_zoom`.`user` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `zoom_user_id` VARCHAR(255),
    `first_name` VARCHAR(255),
    `last_name` VARCHAR(255),

    `is_active` BOOLEAN DEFAULT FALSE,
    `date_created` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    `date_modified` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    INDEX idx_zoom_user_id (`zoom_user_id`)
);

CREATE TABLE IF NOT EXISTS `kopilot_zoom`.`meeting` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `meeting_id` BIGINT UNIQUE NOT NULL,
    `topic` VARCHAR(255) NOT NULL,
    `start_time` DATETIME(6) NOT NULL,
    `schedule_for` VARCHAR(255) NOT NULL,   -- host email

    `meeting_uuid` VARCHAR(255),

    `duration` INT DEFAULT 60,
    `password` VARCHAR(255),
    `is_manual` BOOLEAN DEFAULT FALSE,

    `is_deleted` BOOLEAN DEFAULT FALSE,

    `actual_start_time` DATETIME(6),
    `actual_end_time` DATETIME(6),
    `actual_duration` INT,

    `date_created` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    `date_modified` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    CONSTRAINT `fk_meeting_schedule_for` 
        FOREIGN KEY (`schedule_for`) REFERENCES `user`(`email`) 
        ON DELETE CASCADE ON UPDATE CASCADE,
        
    INDEX `idx_meeting_meeting_id` (`meeting_id`),
    INDEX `idx_meeting_schedule_for` (`schedule_for`),
    INDEX `idx_meeting_start_time` (`start_time`),
    INDEX `idx_meeting_topic` (`topic`)
);

CREATE TABLE IF NOT EXISTS `kopilot_zoom`.`host` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `meeting_id` BIGINT NOT NULL,
    `email` VARCHAR(255) NOT NULL,

    CONSTRAINT `fk_host_meeting`
        FOREIGN KEY (`meeting_id`) REFERENCES `meeting`(`meeting_id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_host_user`
        FOREIGN KEY (`email`) REFERENCES `user`(`email`)
        ON DELETE CASCADE ON UPDATE CASCADE,

    UNIQUE KEY `uk_host_meeting_email` (`meeting_id`, `email`),
);

CREATE TABLE IF NOT EXISTS `kopilot_zoom`.`recording` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `meeting_id` BIGINT NOT NULL,
    `recording_url` VARCHAR(500) NOT NULL,
    `duration` INT,
    `date_created` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    `date_modified` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    CONSTRAINT `fk_recording_meeting_id` 
        FOREIGN KEY (`meeting_id`) REFERENCES `meeting`(`meeting_id`) 
        ON DELETE CASCADE ON UPDATE CASCADE,
        
    INDEX `idx_recording_meeting_id` (`meeting_id`)
);

CREATE TABLE IF NOT EXISTS `kopilot_zoom`.`registrant` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `meeting_id` BIGINT NOT NULL,
    `email` VARCHAR(255) NOT NULL,
    `zoom_registrant_id` VARCHAR(255),
    `first_name` VARCHAR(255),
    `last_name` VARCHAR(255),
    `join_url` VARCHAR(500),
    `participated` BOOLEAN DEFAULT FALSE,
    `date_created` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    `date_modified` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    CONSTRAINT `fk_registrant_meeting_id` 
        FOREIGN KEY (`meeting_id`) REFERENCES `meeting`(`meeting_id`) 
        ON DELETE CASCADE ON UPDATE CASCADE,
        
    UNIQUE KEY `uk_registrant_meeting_email` (`meeting_id`, `email`),
    INDEX `idx_registrant_meeting_id` (`meeting_id`),
    INDEX `idx_registrant_zoom_registrant_id` (`zoom_registrant_id`),
    INDEX `idx_registrant_email` (`email`),
    INDEX `idx_registrant_participated` (`participated`)
);