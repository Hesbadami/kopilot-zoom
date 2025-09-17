import logging

from common.nats_server import nc
from common.mysql import MySQL as db
from common.zoom import ZoomWorkspace as zm
from common.utils import get_utc_datetime

logger = logging.getLogger()

@nc.sub("zoom.sync.meeting")
async def sync_meeting(data: dict):

    meeting_id = data.get("meeting_id")

    meeting_data = await zm.get(f"meetings/{meeting_id}")
    if not meeting_data:
        logger.warning(f"No meeting data for {meeting_id}")
        return
    
    host_id = meeting_data.get("host_id")
    host_email = meeting_data.get("host_email")

    query = """
    INSERT INTO `kopilot_zoom`.`user` (
        `email`, `zoom_user_id`
    ) VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE 
        `zoom_user_id` = VALUES(`zoom_user_id`);
    """
    rowid = await db.aexecute_insert(query, (host_email, host_id))
    if rowid:
        logger.info(f"Inserted new zoom user {host_email}, syncing its data.")
        await nc.pub(
            "zoom.sync.user",
            {
                "email": host_email,
                "zoom_user_id": host_id
            }
        )
    else:
        logger.info(f"Updated zoom user {host_email}.")

    meeting_type = meeting_data.get("type")
    if meeting_type != 2:
        logger.info(f"Wrong meeting type. Ignoring sync request.")
        return
    
    meeting_uuid = meeting_data.get("uuid")
    topic = meeting_data.get("topic")
    start_time = get_utc_datetime(
        meeting_data.get("start_time"), 
        meeting_data.get("timezone")
    )
    duration = meeting_data.get("duration")
    is_manual = not (meeting_data.get("creation_source", "other") == "open_api")
    alternative_hosts = meeting_data.get("settings", {}).get("alternative_hosts", "")

    query = """
    INSERT INTO `kopilot_zoom`.`meeting` (
        `meeting_id`,
        `topic`,
        `start_time`,
        `schedule_for`,
        `meeting_uuid`,
        `duration`,
        `is_manual`
    )
    VALUES
        ( %s, %s, %s, %s, %s, %s, %s )
    ON DUPLICATE KEY UPDATE
        `topic` = VALUES(`topic`),
        `start_time` = VALUES(`start_time`),
        `schedule_for` = VALUES(`schedule_for`),
        `meeting_uuid` = VALUES(`meeting_uuid`),
        `duration` = VALUES(`duration`),
        `is_manual` = VALUES(`is_manual`);
    """
    params = (
        meeting_id,
        topic,
        start_time,
        host_email,
        meeting_uuid,
        duration,
        is_manual
    )
    rowid = await db.aexecute_insert(query, params)
    if rowid:
        logger.info(f"Inserted new meeting, {meeting_id} with synced data. syncing its participation and hosts")
        await nc.pub(
            "zoom.sync.registrants",
            {
                "meeting_id": meeting_id
            }
        )
    else:
        logger.info(f"Updated meeting {meeting_id} to be in sync with zoom workspace.")

    alternative_host_emails = [
        cohost_email.strip() 
        for cohost_email in alternative_hosts.split(";") 
        if cohost_email.strip()
    ] if alternative_hosts.strip() else []

    query = """
    INSERT IGNORE INTO `kopilot_zoom`.`user` (
        `email`
    ) VALUES ( %s );
    """
    rowsaffected = await db.aexecute_many(
        query,
        [(cohost_email,) for cohost_email in alternative_host_emails]
    )

    query = """
    INSERT IGNORE INTO `kopilot_zoom`.`host` (
        `meeting_id`, `email`
    ) VALUES (
        %s, %s
    );
    """
    params_list = [
        (meeting_id, host_email)
    ] + [
        (meeting_id, cohost_email) for cohost_email in alternative_host_emails
    ]
    rowsaffected = await db.aexecute_many(
        query,
        params_list
    )
    
@nc.sub("zoom.sync.user")
async def sync_user(data: dict):
    email = data.get("email")

    user_data = await zm.get(f"users/{email}")
    if not user_data:
        logger.error(f"Failed to fetch user data from zoom workspace: {email}")
        return
    
    zoom_user_id = user_data.get("id")
    first_name = user_data.get("first_name")
    last_name = user_data.get("last_name")
    user_type = user_data.get("type")
    is_active = user_type == 2

    query = """
    INSERT INTO `kopilot_zoom`.`user` (
        `email`,
        `zoom_user_id`,
        `first_name`,
        `last_name`,
        `is_active`
    ) VALUES (
        %s, %s, %s, %s, %s
    )
    ON DUPLICATE KEY UPDATE
        `zoom_user_id` = VALUES(`zoom_user_id`),
        `first_name` = VALUES(`first_name`),
        `last_name` = VALUES(`last_name`),
        `is_active` = VALUES(`is_active`);
    """
    params = (email, zoom_user_id, first_name, last_name, is_active)

    rowid = await db.aexecute_insert(query, params)
    if rowid:
        logger.info(f"Inserted new zoom user {email} with complete sync data.")
    else:
        logger.info(f"Updated zoom user {email} to be in sync with workspace.")

@nc.sub("zoom.sync.registrants")
async def sync_registrants(data: dict):
    
    meeting_id = data.get("meeting_id")

    registrants_page = await zm.get(f"meetings/{meeting_id}/registrants", page_size=300)
    registrants_data = registrants_page.get("registrants")
    if not registrants_data:
        logger.error(f"Failed to get registrants list for meeting {meeting_id}.")
        return
    
    participated_emails = []
    participants_page = await zm.get(f"past_meetings/{meeting_id}/participants", page_size=300)
    if participants_page:
        participants_data = participants_page.get("participants")
        participated_emails = [
            participant.get("email") for participant in participants_data if participant.get("email")
        ]
    
    params_list = []
    for registrant in registrants_data:
        zoom_registrant_id = registrant.get("id")
        first_name = registrant.get("first_name")
        last_name = registrant.get("last_name")
        email = registrant.get("email")
        join_url = registrant.get("join_url")
        participated = email in participated_emails
        params_list.append(
            (meeting_id, email, zoom_registrant_id, first_name, last_name, join_url, participated)
        )
    
    query = """
    INSERT INTO `kopilot_zoom`.`registrant` (
        `meeting_id`,
        `email`,
        `zoom_registrant_id`,
        `first_name`,
        `last_name`,
        `join_url`,
        `participated`
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s
    ) 
    ON DUPLICATE KEY
    UPDATE
        `zoom_registrant_id` = VALUES(`zoom_registrant_id`),
        `first_name` = VALUES(`first_name`),
        `last_name` = VALUES(`last_name`),
        `join_url` = VALUES(`join_url`),
        `participated` = VALUES(`participated`) ;
    """

    rowsaffected = await db.aexecute_many(query, params_list)