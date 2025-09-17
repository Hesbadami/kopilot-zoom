from datetime import datetime
import logging

from common.nats_server import nc
from common.mysql import MySQL as db
from common.utils import get_utc_datetime

logger = logging.getLogger()

@nc.sub("zoom.event")
async def event(data: dict):

    event_id = data['event_id']
    timestamp = datetime.fromisoformat(data.get("timestamp"))
    event_data = data.get("event", {})

    try:

        event_type = event_data.get("event")
        event_ts = event_data.get("event_ts")
        if event_ts:
            event_ts = int(event_ts)
            if event_ts > 1e12:  # likely in milliseconds
                event_time = datetime.fromtimestamp(event_ts / 1000)
            else:
                event_time = datetime.fromtimestamp(event_ts)
        else:
            event_time = datetime.now()
        
        payload = event_data.get("payload", {})
        
        account_id = payload.get("account_id")
        object = payload.get("object", {})

        if event_type == "meeting.created":
            meeting_id = object.get("id")
            meeting = await db.aexecute_query(
                "SELECT * FROM `meeting` WHERE meeting_id = %s LIMIT 1;",
                (meeting_id,),
                fetch_one=True
            )
            if not meeting:
                await nc.pub("zoom.sync.meeting", {
                    "meeting_id": meeting_id
                })
        
        elif event_type == "meeting.deleted":
            meeting_id = object.get("id")
            rowsaffected = await db.aexecute_update(
                "UPDATE `kopilot_zoom`.`meeting` SET `is_deleted` = TRUE WHERE meeting_id = %s;",
                (meeting_id, )
            )

        elif event_type == "meeting.registration_created":
            meeting_id = object.get("id")
            registrant = object.get("registrant", {})
            email = registrant.get("email", "")
            registrant_id = registrant.get("id")

            if ("telegram.local" in email) and (registrant_id):
                query = """
                UPDATE `kopilot_zoom`.`registrant`
                    SET `zoom_registrant_id` = %s
                WHERE `meeting_id` = %s AND `email` = %s;
                """
                params = (registrant_id, meeting_id, email)
                rowsaffected = await db.aexecute_update(query, params)
            
        elif event_type == "meeting.started":
            meeting_id = object.get("id")
            actual_start_time = get_utc_datetime(
                object.get("start_time"),
                object.get("timezone")
            )
            query = """
            UPDATE `kopilot_zoom`.`meeting`
            SET
                `actual_start_time` = %s
            WHERE `meeting_id` = %s;
            """
            params = (actual_start_time, meeting_id)
            rowsaffected = await db.aexecute_update(query, params)

        elif event_type == "meeting.participant_joined":
            meeting_id = object.get("id")
            participant = object.get("participant", {})
            email = participant.get("email")

            query = """
            UPDATE `kopilot_zoom`.`registrant`
                SET `participated` = TRUE
            WHERE `meeting_id` = %s AND `email` = %s;
            """
            rowsaffected = await db.aexecute_update(
                query,
                (meeting_id, email)
            )
            
        elif event_type == "meeting.ended":
            meeting_id = object.get("id")
            actual_start_time = get_utc_datetime(
                object.get("start_time"),
                object.get("timezone")
            )
            actual_end_time = get_utc_datetime(
                object.get("end_time"),
                object.get("timezone")
            )
            duration = object.get("duration")
            query = """
            UPDATE `kopilot_zoom`.`meeting`
            SET
                `actual_start_time` = %s,
                `actual_end_time` = %s,
                `duration` = %s
            WHERE `meeting_id` = %s;
            """
            params = (actual_start_time, actual_end_time, duration, meeting_id)
            rowsaffected = await db.aexecute_update(query, params)
            
        elif event_type == "recording.completed":
            meeting_id = object.get("id")
            share_url = object.get("share_url")
            duration = object.get("duration")

            if share_url:
                query = """
                INSERT INTO `kopilot_zoom`.`recording` (
                    `meeting_id`,
                    `recording_url`,
                    `duration`
                )
                SELECT
                    m.`meeting_id`,
                    %s as `recording_url`,
                    %s as `duration`
                FROM `kopilot_zoom`.`meeting` m
                WHERE m.`meeting_id` = %s;
                """
                params = (share_url, duration, meeting_id)
                rowsaffected = await db.aexecute_update(query, params)

            #TODO publish recording received.

        await nc.pub(
            "zoom.event.processed",
            {
                "event_id": event_id,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    except Exception as e:
        logger.error(f"Error processing event {event_id}")
        await nc.pub(
            "zoom.event.error_processing",
            {
                "event_id": event_id,
                "timestamp": datetime.now().isoformat(),
                "error_message": str(e)
            }
        )


@nc.sub("zoom.event.processed")
async def event_processed(data: dict):

    event_id = data.get('event_id')
    timestamp_str = data.get('timestamp')

    if not event_id or not timestamp_str:
        logger.critical(f"Missing required data: event_id={event_id}, timestamp={timestamp_str}")
        return

    try:
        timestamp = datetime.fromisoformat(timestamp_str)
    except ValueError as e:
        logger.critical(f"Invalid timestamp format: {timestamp_str}, error: {e}")
        return
    
    query = """
    UPDATE `kopilot_events`.`raw_events`
    SET 
        `processed` = TRUE, 
        `processed_at` = %s,
        `status` = 'done'
    WHERE `id` = %s;
    """
    params = (timestamp, event_id)
    updated = await db.aexecute_update(query, params)
    logger.info(f"Updated {updated} event rows as processed.")


@nc.sub("zoom.event.error_processing")
async def event_error_processing(data: dict):

    event_id = data.get('event_id')
    error_message = data.get('error_message')

    if not event_id:
        logger.critical(f"Missing required data: event_id={event_id}")
        return

    query = """
    UPDATE `kopilot_events`.`raw_events`
    SET 
        `status` = 'failed',
        `error_message` = %s,
        `retry_count` = `retry_count` + 1
    WHERE `id` = %s;
    """
    params = (error_message, event_id)
    updated = await db.aexecute_update(query, params)
    logger.info(f"Updated {updated} event rows as failed.")