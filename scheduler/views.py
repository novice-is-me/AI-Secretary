import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import ScheduleSession, Task
from .services.ai_service import parse_tasks_from_text
from .services.ocr_service import extract_text_from_image
from .services.scheduler_service import build_schedule, reshuffle_schedule


@login_required
def dashboard(request):
    latest_session = (
        ScheduleSession.objects.filter(user=request.user)
        .prefetch_related('tasks')
        .first()
    )
    completed_count = 0
    if latest_session:
        completed_count = latest_session.tasks.filter(is_completed=True).count()
    return render(request, 'scheduler/dashboard.html', {
        'session': latest_session,
        'completed_count': completed_count,
    })


@login_required
@require_POST
def generate_schedule(request):
    raw_text = request.POST.get('brain_dump', '').strip()
    image_file = request.FILES.get('schedule_image')

    if not raw_text and not image_file:
        return JsonResponse({'error': 'Please provide text or an image.'}, status=400)

    # OCR path
    if image_file and not raw_text:
        try:
            raw_text = extract_text_from_image(image_file)
        except Exception as e:
            return JsonResponse({'error': f'OCR failed: {str(e)}'}, status=500)

    if not raw_text:
        return JsonResponse({'error': 'Could not extract text from image.'}, status=400)

    # Parse tasks via GPT
    try:
        parsed_tasks = parse_tasks_from_text(raw_text)
    except Exception as e:
        return JsonResponse({'error': f'AI parsing failed: {str(e)}'}, status=500)

    if not parsed_tasks:
        return JsonResponse({'error': 'No tasks found in your input.'}, status=400)

    # Build schedule
    scheduled = build_schedule(parsed_tasks)

    # Persist to DB
    session = ScheduleSession.objects.create(
        user=request.user,
        raw_input=raw_text,
        schedule_date=date.today(),
    )
    if image_file:
        session.input_image = image_file
        session.save()

    for item in scheduled:
        from datetime import time as dtime
        fixed_time = None
        if item.get('fixed_time'):
            try:
                parts = item['fixed_time'].split(':')
                fixed_time = dtime(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                pass

        sched_start = None
        sched_end = None
        try:
            parts = item['scheduled_start'].split(':')
            sched_start = dtime(int(parts[0]), int(parts[1]))
            parts = item['scheduled_end'].split(':')
            sched_end = dtime(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError, AttributeError):
            pass

        Task.objects.create(
            session=session,
            title=item['title'],
            duration_minutes=item['duration_minutes'],
            fixed_time=fixed_time,
            priority=item.get('priority', 'medium'),
            notes=item.get('notes', ''),
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
    incomplete_tasks = session.tasks.filter(is_completed=False)

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

    if not tasks_data:
        return redirect('dashboard')

    rescheduled = reshuffle_schedule(tasks_data)

    # Update task times in place
    task_map = {t.title: t for t in incomplete_tasks}
    for i, item in enumerate(rescheduled):
        task = task_map.get(item['title'])
        if task:
            from datetime import time as dtime
            try:
                parts = item['scheduled_start'].split(':')
                task.scheduled_start = dtime(int(parts[0]), int(parts[1]))
                parts = item['scheduled_end'].split(':')
                task.scheduled_end = dtime(int(parts[0]), int(parts[1]))
                task.order = i
                task.save()
            except (ValueError, IndexError):
                pass

    session.is_reshuffled = True
    session.save()

    return redirect('dashboard')
