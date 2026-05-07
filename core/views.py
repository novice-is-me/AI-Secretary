import json
import re
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import UserProfile

DEFAULT_PROFILE_IMAGE_URL = 'https://lh3.googleusercontent.com/aida-public/AB6AXuAEKKx_LNveGYkwrZFX_FhOd-isF0dMjkcvIQpC13iNpsPh2HD4IOcU7QSW4FM-iiAQX7xfFrqJnJotorPSydNtr3EZkOPqHSq_fpndTO5foeZh0Ikj9Q_jO2wv3CKOpuvON0lTvKj4XJjBVshyon3-ilBgNff0ieS8P6SeOOnhYWU6KNPgitE1W79LQIXRwP_tssPyIIKOKgUnHjp72_YmDF8yxJl9ProCY3G9ZuDEMfCuZp1D2SrPzhRciKxj1n6nTLFCGAFrOodz'


# ─────────────────────────────────────────────
# AUTH VIEWS
# ─────────────────────────────────────────────

def login_view(request):
    if request.method == "POST":
        login_input = request.POST.get("email")
        password = request.POST.get("password")

        username = login_input

        try:
            user_obj = User.objects.get(email__iexact=login_input)
            username = user_obj.username
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("huddle")

        return render(request, "login.html", {
            "error": "Invalid email or password"
        })

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return render(request, 'logout.html')


def register_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, 'register.html')

        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            messages.error(request, 'An account with this email already exists.')
            return render(request, 'register.html')

        first_name, _, last_name = full_name.partition(' ')
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        login(request, user)
        UserProfile.objects.get_or_create(user=user)
        messages.success(request, f'Welcome, {user.first_name or user.username}!')
        return redirect('huddle')

    return render(request, 'register.html')


# ─────────────────────────────────────────────
# PAGE VIEWS
# ─────────────────────────────────────────────

def home(request):
    return render(request, 'home.html')


def _profile_context(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    display_name = user.get_full_name().strip() or user.email or user.username
    return {
        'profile': profile,
        'display_name': display_name,
        'profile_image_url': profile.avatar_data or DEFAULT_PROFILE_IMAGE_URL,
    }


@login_required
@ensure_csrf_cookie
def huddle_view(request):
    return render(request, 'huddle.html', _profile_context(request.user))


@login_required
def timeline_view(request):
    context = _profile_context(request.user)
    profile = context['profile']
    schedule = profile.schedule or request.session.get('schedule', [])
    tasks = profile.parsed_tasks or request.session.get('parsed_tasks', [])
    today = _normalize_schedule_date()
    
    time_range = ''
    if schedule:
        time_range = f"{schedule[0]['start_time']} – {schedule[-1]['end_time']}"
 
    context.update({
        'schedule': schedule,
        'tasks':    tasks,
        'has_data': bool(schedule),
        'time_range': time_range,
        'today': today,
    })
    return render(request, 'timeline.html', context)


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        bio = request.POST.get('bio', '').strip()
        avatar_data = request.POST.get('avatar_data', '').strip()

        if not full_name:
            messages.error(request, 'Full name is required.')
            return redirect('profile')

        if not email:
            messages.error(request, 'Email is required.')
            return redirect('profile')

        email_taken = User.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists()
        username_taken = User.objects.filter(username__iexact=email).exclude(pk=request.user.pk).exists()
        if email_taken or username_taken:
            messages.error(request, 'That email is already used by another account.')
            return redirect('profile')

        first_name, _, last_name = full_name.partition(' ')
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.email = email
        request.user.username = email
        request.user.save()

        profile.bio = bio
        if avatar_data:
            profile.avatar_data = avatar_data
        profile.save()

        messages.success(request, 'Profile saved.')
        return redirect('profile')

    context = _profile_context(request.user)
    context.update({
        'user': request.user,
    })
    return render(request, 'profile.html', context)


# ─────────────────────────────────────────────
# TASK PARSING AND SCHEDULING
# ─────────────────────────────────────────────

PRIORITY_KEYWORDS = {
    'high':   ['urgent', 'asap', 'critical', 'deadline', 'due today', 'important', 'must', 'immediately', 'meeting', 'standup', 'appointment', 'interview'],
    'medium': ['study', 'call', 'review', 'submit', 'send', 'prepare', 'finish', 'complete'],
    'low':    ['read', 'check', 'look into', 'maybe', 'consider', 'optional', 'sometime', 'whenever'],
}

DURATION_HINTS = (
    (r'\b(\d+)\s*hours?\b', lambda m: int(m.group(1)) * 60),
    (r'\b(\d+)\s*hrs?\b',   lambda m: int(m.group(1)) * 60),
    (r'\b(\d+)\s*minutes?\b', lambda m: int(m.group(1))),
    (r'\b(\d+)\s*mins?\b',  lambda m: int(m.group(1))),
)

TIME_HINT = re.compile(r'\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', re.IGNORECASE)


def _estimate_priority(text):
    t = text.lower()
    for level, keywords in PRIORITY_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return level
    return 'medium'


def _estimate_duration(text):
    t = text.lower()
    for pattern, extractor in DURATION_HINTS:
        m = re.search(pattern, t)
        if m:
            return extractor(m)
    return {'high': 45, 'medium': 30, 'low': 20}[_estimate_priority(text)]


def _extract_time(text):
    for match in TIME_HINT.finditer(text):
        suffix = text[match.end():match.end() + 12].lower()
        if re.match(r'\s*(?:hours?|hrs?|minutes?|mins?)\b', suffix):
            continue

        has_colon = bool(match.group(2))
        has_meridiem = bool(match.group(3))
        has_at_prefix = text[max(0, match.start() - 3):match.start()].lower().strip() == 'at'
        if not has_colon and not has_meridiem and not has_at_prefix:
            continue

        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = (match.group(3) or '').lower()

        if hour > 24 or minute > 59:
            continue
        if meridiem == 'pm' and hour != 12:
            hour += 12
        if meridiem == 'am' and hour == 12:
            hour = 0
        if not meridiem and hour > 23:
            continue
        return f'{hour:02d}:{minute:02d}'
    return None


def _clean_task_title(text):
    title = text.strip()
    title = re.sub(r'\b(?:today|tomorrow|tonight|this morning|this afternoon|this evening)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bfor\s+\d+\s*(?:hours?|hrs?|minutes?|mins?)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip(' -,:;')
    return title or text.strip()


def _split_task_clauses(raw_text):
    clauses = []
    for line in re.split(r'[\n\r;]+', raw_text.strip()):
        for clause in re.split(r',\s*', line):
            cleaned = re.sub(r'^[\s\-\*\•\d\.\)]+', '', clause).strip()
            if cleaned:
                clauses.append(cleaned)
    return clauses


def _parse_raw_tasks(raw_text):
    tasks = []
    for i, line in enumerate(_split_task_clauses(raw_text)):
        priority = _estimate_priority(line)
        duration = _estimate_duration(line)
        scheduled_time = _extract_time(line)
        title = _clean_task_title(line)
        tasks.append({
            'id': i + 1,
            'title': title,
            'task': title,
            'priority': priority.title(),
            'priority_key': priority,
            'duration_minutes': duration,
            'duration': duration,
            'time': scheduled_time,
        })
    return tasks


def _normalize_schedule_date(value=None):
    today = timezone.localdate()
    if not value:
        return today.isoformat()
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date().isoformat()
    except (TypeError, ValueError):
        return today.isoformat()


def _task_schedule_date(task, fallback_date):
    return _normalize_schedule_date(task.get('schedule_date') or task.get('date') or fallback_date)


def _minutes(time_value):
    hour, minute = [int(part) for part in time_value.split(':')]
    return hour * 60 + minute


def _time_label(total_minutes):
    total_minutes = max(0, total_minutes)
    return f'{total_minutes // 60:02d}:{total_minutes % 60:02d}'


def _find_open_start(occupied, earliest, duration):
    candidate = earliest
    for start, end in sorted(occupied):
        if candidate + duration <= start:
            break
        if candidate < end:
            candidate = end + 10
    return candidate


def _generate_schedule(tasks, start_hour=9, schedule_date=None):
    schedule_date = _normalize_schedule_date(schedule_date)
    order = {'high': 0, 'medium': 1, 'low': 2}
    sorted_tasks = sorted(
        tasks,
        key=lambda t: (
            t.get('time') is None,
            t.get('time') or '',
            order.get(str(t.get('priority_key') or t.get('priority', 'medium')).lower(), 1),
        ),
    )
    schedule = []
    occupied = []
    current_minutes = max(0, min(23, start_hour)) * 60

    for task in sorted_tasks:
        priority_key = str(task.get('priority_key') or task.get('priority', 'medium')).lower()
        duration = int(task.get('duration_minutes') or task.get('duration') or 30)
        if task.get('time'):
            start_minutes = _find_open_start(occupied, _minutes(task['time']), duration)
        else:
            start_minutes = _find_open_start(occupied, current_minutes, duration)
        end_minutes = start_minutes + duration
        title = task.get('title') or task.get('task') or 'Untitled task'
        schedule.append({
            **task,
            'title': title,
            'task': title,
            'priority': priority_key.title(),
            'priority_key': priority_key,
            'time': _time_label(start_minutes),
            'start_time': _time_label(start_minutes),
            'end_time': _time_label(end_minutes),
            'duration_minutes': duration,
            'duration': duration,
            'schedule_date': schedule_date,
        })
        occupied.append((start_minutes, end_minutes))
        if not task.get('time'):
            current_minutes = end_minutes + 10
    return sorted(schedule, key=lambda item: (item['schedule_date'], item['start_time']))


def _task_title_key(task):
    return str(task.get('title') or task.get('task') or '').strip().lower()


def _merge_task_inputs(existing_tasks, incoming_tasks, schedule_date):
    if incoming_tasks is None:
        return list(existing_tasks or [])

    merged = [dict(task) for task in (existing_tasks or [])]
    existing_ids = {str(task.get('id')) for task in merged if task.get('id') is not None}
    numeric_ids = [int(task_id) for task_id in existing_ids if task_id.isdigit()]
    next_id = (max(numeric_ids) + 1) if numeric_ids else 1

    for incoming in incoming_tasks:
        incoming_date = _task_schedule_date(incoming, schedule_date)
        incoming_key = _task_title_key(incoming)
        match_index = None

        for idx, existing in enumerate(merged):
            if _task_schedule_date(existing, schedule_date) != incoming_date:
                continue
            if incoming_key and _task_title_key(existing) == incoming_key:
                match_index = idx
                break

        normalized = {**incoming, 'schedule_date': incoming_date}
        if match_index is not None:
            normalized['id'] = merged[match_index].get('id') or normalized.get('id') or next_id
            merged[match_index] = {**merged[match_index], **normalized}
            existing_ids.add(str(normalized['id']))
            continue

        if normalized.get('id') is None or str(normalized.get('id')) in existing_ids:
            normalized['id'] = next_id
            next_id += 1
        existing_ids.add(str(normalized['id']))
        merged.append(normalized)

    return merged


def _api_success(data):
    return {'success': True, 'data': data, 'error': None}


def _api_error(message):
    return {'success': False, 'data': None, 'error': message}


# ─────────────────────────────────────────────
# API ENDPOINTS
# named to match core/urls.py imports exactly
# ─────────────────────────────────────────────

@login_required
@require_POST
def parse_text(request):
    """POST /parse-text/  ->  { success, data: { tasks }, error }"""
    try:
        body = json.loads(request.body)
        raw  = body.get('text', '').strip()
    except (json.JSONDecodeError, AttributeError):
        raw = request.POST.get('text', '').strip()

    if not raw:
        return JsonResponse({**_api_error('No text provided.'), 'tasks': []}, status=400)

    schedule_date = _normalize_schedule_date(body.get('schedule_date') if 'body' in locals() else request.POST.get('schedule_date'))
    tasks = [{**task, 'schedule_date': schedule_date} for task in _parse_raw_tasks(raw)]
    request.session['parsed_tasks'] = tasks
    return JsonResponse({**_api_success({'tasks': tasks}), 'tasks': tasks})


@login_required
@require_POST
def upload_image(request):
    """POST /upload-image/  ->  { success, data: { extracted_text, tasks }, error }"""
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({**_api_error('No image uploaded.'), 'tasks': []}, status=400)

    extracted = _ocr_extract(image_file)
    schedule_date = _normalize_schedule_date(request.POST.get('schedule_date'))
    tasks = [{**task, 'schedule_date': schedule_date} for task in _parse_raw_tasks(extracted)]
    request.session['parsed_tasks'] = tasks
    return JsonResponse({
        **_api_success({'extracted_text': extracted, 'tasks': tasks}),
        'extracted_text': extracted,
        'tasks': tasks,
    })


def _ocr_extract(image_file):
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(image_file))
    except Exception:
        # Graceful fallback keeps the demo alive without pytesseract
        return (
            'Review project proposal\n'
            'Urgent: send budget report\n'
            'Team standup at 10am\n'
            'Read documentation for new API\n'
        )


@login_required
@require_POST
def generate_schedule(request):
    """POST /generate-schedule/  ->  { success, data: { schedule }, error }"""
    try:
        body       = json.loads(request.body)
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        start_hour = int(body.get('start_hour', 9))
        schedule_date = _normalize_schedule_date(body.get('schedule_date'))
        reshuffle = bool(body.get('reshuffle'))
        stored_tasks = profile.parsed_tasks or request.session.get('parsed_tasks', [])
        tasks = _merge_task_inputs(stored_tasks, body.get('tasks'), schedule_date)
    except (json.JSONDecodeError, AttributeError, ValueError):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        tasks      = request.session.get('parsed_tasks', []) or profile.parsed_tasks
        start_hour = 9
        schedule_date = _normalize_schedule_date()
        reshuffle = False

    if not tasks:
        return JsonResponse({**_api_error('No tasks to schedule.'), 'schedule': []}, status=400)

    normalized_tasks = []
    for i, task in enumerate(tasks):
        task_date = _task_schedule_date(task, schedule_date)
        normalized = {**task, 'id': task.get('id') or i + 1, 'schedule_date': task_date}
        if reshuffle and task_date == schedule_date:
            normalized['time'] = None
        normalized_tasks.append(normalized)

    selected_tasks = [task for task in normalized_tasks if _task_schedule_date(task, schedule_date) == schedule_date]
    if not selected_tasks:
        return JsonResponse({**_api_error('No tasks for this date.'), 'schedule': []}, status=400)

    day_schedule = _generate_schedule(selected_tasks, start_hour=start_hour, schedule_date=schedule_date)
    scheduled_by_id = {
        str(item.get('id')): item
        for item in day_schedule
        if item.get('id') is not None
    }
    scheduled_by_title = {
        item.get('title') or item.get('task'): item
        for item in day_schedule
    }
    normalized_tasks = [
        {
            **task,
            **({
                'time': scheduled['start_time'],
                'start_time': scheduled['start_time'],
                'end_time': scheduled['end_time'],
            } if (scheduled := (
                scheduled_by_id.get(str(task.get('id')))
                or scheduled_by_title.get(task.get('title') or task.get('task'))
            )) and _task_schedule_date(task, schedule_date) == schedule_date else {}),
        }
        for task in normalized_tasks
    ]
    preserved_schedule = [
        item for item in (profile.schedule or request.session.get('schedule', []))
        if _task_schedule_date(item, schedule_date) != schedule_date
    ]
    schedule = sorted(preserved_schedule + day_schedule, key=lambda item: (item.get('schedule_date', schedule_date), item.get('start_time', '00:00')))
    request.session['schedule'] = schedule
    request.session['parsed_tasks'] = normalized_tasks
    profile.parsed_tasks = normalized_tasks
    profile.schedule = schedule
    profile.save(update_fields=['parsed_tasks', 'schedule'])
    return JsonResponse({
        **_api_success({'schedule': schedule}),
        'schedule': schedule,
        'redirect': '/timeline/',
    })


@login_required
@require_POST
def delete_task(request):
    try:
        body = json.loads(request.body)
        task_id = body.get('id')
        title = body.get('title') or body.get('task')
        schedule_date = _normalize_schedule_date(body.get('schedule_date'))
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse(_api_error('Invalid request.'), status=400)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    def matches(item):
        same_date = _task_schedule_date(item, schedule_date) == schedule_date
        same_id = task_id is not None and str(item.get('id')) == str(task_id)
        same_title = title and (item.get('title') == title or item.get('task') == title)
        return same_date and (same_id or same_title)

    profile.parsed_tasks = [task for task in (profile.parsed_tasks or []) if not matches(task)]
    profile.schedule = [item for item in (profile.schedule or []) if not matches(item)]
    profile.save(update_fields=['parsed_tasks', 'schedule'])
    request.session['parsed_tasks'] = profile.parsed_tasks
    request.session['schedule'] = profile.schedule
    return JsonResponse({**_api_success({'tasks': profile.parsed_tasks, 'schedule': profile.schedule}), 'tasks': profile.parsed_tasks, 'schedule': profile.schedule})
