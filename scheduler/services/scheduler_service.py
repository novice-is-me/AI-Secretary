from datetime import datetime, date, time, timedelta
from typing import Optional


PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2}
DAY_START_HOUR = 8   # 8:00 AM
DAY_END_HOUR = 22    # 10:00 PM


def _to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _from_minutes(minutes: int) -> time:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return time(minutes // 60, minutes % 60)


def _parse_fixed_time(fixed_time_str: Optional[str]) -> Optional[time]:
    if not fixed_time_str:
        return None
    try:
        return time.fromisoformat(fixed_time_str)
    except (ValueError, TypeError):
        return None


def build_schedule(tasks_data: list[dict], start_from: Optional[time] = None) -> list[dict]:
    """
    Takes raw parsed task dicts and returns them with scheduled_start/scheduled_end filled in.

    tasks_data items: {title, duration_minutes, fixed_time (str|None), priority, notes}
    Returns same dicts plus: scheduled_start (str HH:MM), scheduled_end (str HH:MM), order (int)
    """
    if start_from is None:
        start_from = time(DAY_START_HOUR, 0)

    day_start = _to_minutes(start_from)
    day_end = DAY_END_HOUR * 60

    # Separate fixed-time and flexible tasks
    fixed_tasks = []
    flexible_tasks = []

    for task in tasks_data:
        ft = _parse_fixed_time(task.get('fixed_time'))
        if ft:
            fixed_tasks.append({**task, '_fixed_time_obj': ft})
        else:
            flexible_tasks.append(task)

    # Sort fixed tasks by their time
    fixed_tasks.sort(key=lambda t: _to_minutes(t['_fixed_time_obj']))

    # Sort flexible tasks by priority
    flexible_tasks.sort(key=lambda t: PRIORITY_ORDER.get(t.get('priority', 'medium'), 1))

    # Build occupied intervals from fixed tasks
    occupied = []
    for task in fixed_tasks:
        ft = task['_fixed_time_obj']
        start_min = _to_minutes(ft)
        end_min = start_min + int(task.get('duration_minutes', 30))
        occupied.append((start_min, end_min))

    # Find free slots
    def find_free_slots(occupied_intervals: list, day_s: int, day_e: int) -> list[tuple]:
        sorted_occ = sorted(occupied_intervals)
        slots = []
        cursor = day_s
        for s, e in sorted_occ:
            if cursor < s:
                slots.append((cursor, s))
            cursor = max(cursor, e)
        if cursor < day_e:
            slots.append((cursor, day_e))
        return slots

    free_slots = find_free_slots(occupied, day_start, day_end)

    # Schedule flexible tasks into free slots
    slot_idx = 0
    slot_cursor = free_slots[0][0] if free_slots else day_start
    flex_scheduled = []

    for task in flexible_tasks:
        duration = int(task.get('duration_minutes', 30))
        scheduled = False

        while slot_idx < len(free_slots):
            slot_start, slot_end = free_slots[slot_idx]
            available = slot_end - max(slot_cursor, slot_start)

            if slot_cursor < slot_start:
                slot_cursor = slot_start

            if available >= duration:
                start_min = slot_cursor
                end_min = slot_cursor + duration
                flex_scheduled.append({**task, '_sched_start': start_min, '_sched_end': end_min})
                slot_cursor = end_min
                scheduled = True
                break
            else:
                slot_idx += 1
                if slot_idx < len(free_slots):
                    slot_cursor = free_slots[slot_idx][0]

        if not scheduled:
            # Schedule beyond day end (overflow)
            overflow_start = day_end
            if flex_scheduled:
                overflow_start = flex_scheduled[-1]['_sched_end']
            flex_scheduled.append({
                **task,
                '_sched_start': overflow_start,
                '_sched_end': overflow_start + duration,
            })

    # Combine and sort all scheduled tasks
    all_scheduled = []

    for task in fixed_tasks:
        ft = task['_fixed_time_obj']
        s = _to_minutes(ft)
        e = s + int(task.get('duration_minutes', 30))
        all_scheduled.append({**task, '_sched_start': s, '_sched_end': e})

    all_scheduled.extend(flex_scheduled)
    all_scheduled.sort(key=lambda t: t['_sched_start'])

    result = []
    for i, task in enumerate(all_scheduled):
        result.append({
            'title': task.get('title', ''),
            'duration_minutes': task.get('duration_minutes', 30),
            'fixed_time': task.get('fixed_time'),
            'priority': task.get('priority', 'medium'),
            'notes': task.get('notes', ''),
            'scheduled_start': _from_minutes(task['_sched_start']).strftime('%H:%M'),
            'scheduled_end': _from_minutes(task['_sched_end']).strftime('%H:%M'),
            'order': i,
        })

    return result


def reshuffle_schedule(remaining_tasks_data: list[dict]) -> list[dict]:
    """Re-schedule only unfinished tasks starting from now."""
    now = datetime.now().time()
    # Round up to next 15-min block
    minutes = _to_minutes(now)
    rounded = ((minutes + 14) // 15) * 15
    start_from = _from_minutes(rounded)
    return build_schedule(remaining_tasks_data, start_from=start_from)
