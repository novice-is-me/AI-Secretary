from datetime import datetime
from django import template

register = template.Library()

TIMELINE_START_HOUR = 8
PX_PER_MINUTE = 1.2


@register.filter
def time_to_px(t):
    """Convert a time → pixel offset from 8 AM."""
    if not t:
        return 0
    minutes = (t.hour - TIMELINE_START_HOUR) * 60 + t.minute
    return max(0, round(minutes * PX_PER_MINUTE))


@register.filter
def dur_to_px(minutes):
    """Convert duration in minutes → pixel height (min 38px so text is readable)."""
    return max(38, round(int(minutes) * PX_PER_MINUTE))


@register.filter
def gcal_dt(t, schedule_date):
    """Combine time + date → GCal URL datetime string: YYYYMMDDTHHmmSS."""
    if not t or not schedule_date:
        return ''
    return datetime.combine(schedule_date, t).strftime('%Y%m%dT%H%M%S')
