from collections import defaultdict
from datetime import date, time as dtime, datetime, timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import ScheduleSession, Task
from .services.ai_service import parse_tasks_from_text
from .services.ocr_service import extract_text_from_image
from .services.scheduler_service import build_schedule, reshuffle_schedule

TIMELINE_START_HOUR = 8
TIMELINE_END_HOUR = 22
PX_PER_MINUTE = 1.2

WEEKDAY_MAP = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6,
}


def _resolve_day(day_str: str | None, today: date) -> date:
    if not day_str:
        return today
    d = day_str.strip()
    dl = d.lower()
    if dl in ('today', ''):
        return today
    if dl == 'tomorrow':
        return today + timedelta(days=1)
    # ISO date string e.g. "2026-05-13"
    try:
        return date.fromisoformat(d)
    except (ValueError, TypeError):
        pass
    dl = dl.replace('next ', '')
    if dl in WEEKDAY_MAP:
        target = WEEKDAY_MAP[dl]
        days_ahead = (target - today.weekday()) % 7
        return today + timedelta(days=days_ahead)
    return today


def _timeline_context():
    hours = [
        {
            'label': f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}",
            'top': int((h - TIMELINE_START_HOUR) * 60 * PX_PER_MINUTE),
        }
        for h in range(TIMELINE_START_HOUR, TIMELINE_END_HOUR + 1)
    ]
    height = int((TIMELINE_END_HOUR - TIMELINE_START_HOUR) * 60 * PX_PER_MINUTE)
    return {'timeline_hours': hours, 'timeline_height': height}


def _build_day_plans(session, today: date):
    """Always return 7 days starting from today, merging in any session tasks."""
    tasks_by_date = defaultdict(list)
    for task in session.tasks.all():
        task_date = task.task_date or session.schedule_date
        tasks_by_date[task_date].append(task)

    # Base 7-day window
    window = {today + timedelta(days=i) for i in range(7)}
    # Include any task dates outside the window too
    all_dates = sorted(window | set(tasks_by_date.keys()))

    plans = []
    for d in all_dates:
        day_tasks = tasks_by_date.get(d, [])
        plans.append({
            'date': d,
            'tasks': day_tasks,
            'total': len(day_tasks),
            'completed': sum(1 for t in day_tasks if t.is_completed),
            'is_today': d == today,
        })
    return plans


@login_required
def dashboard(request):
    latest_session = (
        ScheduleSession.objects.filter(user=request.user)
        .prefetch_related('tasks')
        .first()
    )

    day_plans = []
    total_count = completed_count = 0

    if latest_session:
        day_plans = _build_day_plans(latest_session, date.today())
        total_count = sum(d['total'] for d in day_plans)
        completed_count = sum(d['completed'] for d in day_plans)

    ctx = {
        'session': latest_session,
        'day_plans': day_plans,
        'total_count': total_count,
        'completed_count': completed_count,
        'today': date.today(),
    }
    ctx.update(_timeline_context())
    return render(request, 'scheduler/dashboard.html', ctx)


@login_required
@require_POST
def generate_schedule(request):
    raw_text = request.POST.get('brain_dump', '').strip()
    image_file = request.FILES.get('schedule_image')

    if not raw_text and not image_file:
        messages.error(request, 'Please enter some tasks or upload a screenshot.')
        return redirect('dashboard')

    if image_file and not raw_text:
        try:
            raw_text = extract_text_from_image(image_file)
        except Exception as e:
            messages.error(request, f'Could not read your image. Try typing tasks instead. ({e})')
            return redirect('dashboard')

    if not raw_text:
        messages.error(request, 'No text could be extracted from the image.')
        return redirect('dashboard')

    today = date.today()

    try:
        parsed_tasks = parse_tasks_from_text(raw_text, today=today)
    except Exception as e:
        messages.error(request, f'AI parsing failed: {e}')
        return redirect('dashboard')

    if not parsed_tasks:
        messages.error(request, 'No tasks found in your input. Try being more specific.')
        return redirect('dashboard')

    # Resolve the "day" field to actual dates, then group and schedule per day
    for task in parsed_tasks:
        task['_task_date'] = _resolve_day(task.get('day'), today)

    by_date = defaultdict(list)
    for task in parsed_tasks:
        by_date[task['_task_date']].append(task)

    all_scheduled = []
    for task_date, day_tasks in sorted(by_date.items()):
        scheduled = build_schedule(day_tasks)
        for item in scheduled:
            item['_task_date'] = task_date
        all_scheduled.extend(scheduled)

    # Reuse existing session so the calendar isn't wiped on every submit
    session = ScheduleSession.objects.filter(user=request.user).first()
    if session:
        session.raw_input = (session.raw_input + '\n---\n' + raw_text).strip()
        if image_file:
            session.input_image = image_file
        session.save()
    else:
        session = ScheduleSession.objects.create(
            user=request.user,
            raw_input=raw_text,
            schedule_date=today,
        )
        if image_file:
            session.input_image = image_file
            session.save()

    for item in all_scheduled:
        fixed_time = None
        if item.get('fixed_time'):
            try:
                h, m = item['fixed_time'].split(':')
                fixed_time = dtime(int(h), int(m))
            except (ValueError, IndexError):
                pass

        sched_start = sched_end = None
        try:
            h, m = item['scheduled_start'].split(':')
            sched_start = dtime(int(h), int(m))
            h, m = item['scheduled_end'].split(':')
            sched_end = dtime(int(h), int(m))
        except (ValueError, IndexError, AttributeError):
            pass

        Task.objects.create(
            session=session,
            title=item['title'],
            duration_minutes=item['duration_minutes'],
            fixed_time=fixed_time,
            priority=item.get('priority', 'medium'),
            notes=item.get('notes', ''),
            task_date=item['_task_date'],
            scheduled_start=sched_start,
            scheduled_end=sched_end,
            order=item.get('order', 0),
        )

    return redirect('dashboard')


@login_required
@require_POST
def toggle_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, session__user=request.user)
    task.is_completed = not task.is_completed
    task.save()
    return JsonResponse({'completed': task.is_completed})


@login_required
@require_POST
def reshuffle(request, session_id):
    session = get_object_or_404(ScheduleSession, id=session_id, user=request.user)

    # Only reshuffle tasks for the date passed in POST (defaults to today)
    raw_date = request.POST.get('task_date', '')
    try:
        reshuffle_date = date.fromisoformat(raw_date)
    except (ValueError, TypeError):
        reshuffle_date = date.today()

    incomplete_tasks = list(
        session.tasks.filter(is_completed=False, task_date=reshuffle_date)
    )
    # Fallback: if no tasks with task_date match, try session.schedule_date tasks
    if not incomplete_tasks:
        incomplete_tasks = list(
            session.tasks.filter(is_completed=False, task_date__isnull=True)
        )

    if not incomplete_tasks:
        messages.info(request, 'All tasks for that day are already completed!')
        return redirect(f"{request.build_absolute_uri('/dashboard/')}?day={reshuffle_date}")

    tasks_data = [
        {
            'title': t.title,
            'duration_minutes': t.duration_minutes,
            'fixed_time': t.fixed_time.strftime('%H:%M') if t.fixed_time else None,
            'priority': t.priority,
            'notes': t.notes,
        }
        for t in incomplete_tasks
    ]

    rescheduled = reshuffle_schedule(tasks_data)
    task_map = {t.title: t for t in incomplete_tasks}

    for i, item in enumerate(rescheduled):
        task = task_map.get(item['title'])
        if task:
            try:
                h, m = item['scheduled_start'].split(':')
                task.scheduled_start = dtime(int(h), int(m))
                h, m = item['scheduled_end'].split(':')
                task.scheduled_end = dtime(int(h), int(m))
                task.order = i
                task.save()
            except (ValueError, IndexError):
                pass

    session.is_reshuffled = True
    session.save()

    messages.success(request, 'Schedule reshuffled from now!')
    return redirect(f'/dashboard/?day={reshuffle_date}')


@login_required
def export_ics(request, session_id):
    session = get_object_or_404(ScheduleSession, id=session_id, user=request.user)
    tasks = session.tasks.filter(scheduled_start__isnull=False)

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//SecAI//Hackathon//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:SecAI {session.schedule_date}',
    ]

    def esc(s):
        return str(s).replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;').replace('\n', '\\n')

    for task in tasks:
        task_date = task.task_date or session.schedule_date
        dt_start = datetime.combine(task_date, task.scheduled_start)
        dt_end = (
            datetime.combine(task_date, task.scheduled_end)
            if task.scheduled_end
            else dt_start + timedelta(minutes=task.duration_minutes)
        )

        desc = task.notes or f'{task.priority} priority'
        lines += [
            'BEGIN:VEVENT',
            f'UID:task-{task.id}@tempo',
            f'SUMMARY:{esc(task.title)}',
            f'DTSTART:{dt_start.strftime("%Y%m%dT%H%M%S")}',
            f'DTEND:{dt_end.strftime("%Y%m%dT%H%M%S")}',
            f'DESCRIPTION:{esc(desc)}',
            f'CATEGORIES:{task.priority.upper()}',
            'END:VEVENT',
        ]

    lines.append('END:VCALENDAR')

    response = HttpResponse('\r\n'.join(lines), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="tempo-{session.schedule_date}.ics"'
    return response


@login_required
@require_POST
def reset_schedule(request):
    ScheduleSession.objects.filter(user=request.user).delete()
    messages.success(request, 'Plan cleared. Start fresh whenever you\'re ready.')
    return redirect('dashboard')


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})
