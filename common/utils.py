from datetime import datetime
import zoneinfo

def get_utc_datetime(start_time, timezone):
    if start_time.endswith('Z'):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    else:
        start_time = datetime.fromisoformat(start_time)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=zoneinfo.ZoneInfo(timezone))
    else:
        start_time = start_time.astimezone(zoneinfo.ZoneInfo(timezone))
    start_time = start_time.astimezone(zoneinfo.ZoneInfo("UTC"))
    return start_time