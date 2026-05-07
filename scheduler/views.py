from datetime import date, time as dtime

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
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
    total_count = 0
    completed_count = 0
    if latest_session:
        all_tasks = list(latest_session.tasks.all())
        total_count = len(all_tasks)
        completed_count = sum(1 for t in all_tasks if t.is_completed)
    return render(request, 'scheduler/dashboard.html', {
        'session': latest_session,
        'total_count': total_count,
        'completed_count': completed_count,
    })


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
            messages.error(request, f'Could not read your image. Try typing your tasks instead. ({e})')
            return redirect('dashboard')

    if not raw_text:
        messages.error(request, 'No text could be extracted from the image.')
        return redirect('dashboard')

    try:
        parsed_tasks = parse_tasks_from_text(raw_text)
    except Exception as e:
        messages.error(request, f'AI parsing failed: {e}')
        return redirect('dashboard')

    if not parsed_tasks:
        messages.error(request, 'No tasks found in your input. Try being more specific.')
        return redirect('dashboard')

    scheduled = build_schedule(parsed_tasks)

    session = ScheduleSession.objects.create(
        user=request.user,
        raw_input=raw_text,
        schedule_date=date.today(),
    )
    if image_file:
        session.input_image = image_file
        session.save()

    for item in scheduled:
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
    incomplete_tasks = list(session.tasks.filter(is_completed=False))

    if not incomplete_tasks:
        messages.info(request, 'All tasks are already completed!')
        return redirect('dashboard')

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
