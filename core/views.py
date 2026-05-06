import json
import re
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
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
    
    time_range = ''
    if schedule:
        time_range = f"{schedule[0]['start_time']} – {schedule[-1]['end_time']}"
 
    context.update({
        'schedule': schedule,
        'tasks':    tasks,
        'has_data': bool(schedule),
        'time_range': time_range,
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
# MOCK AI PIPELINE
# ─────────────────────────────────────────────

PRIORITY_KEYWORDS = {
    'high':   ['urgent', 'asap', 'critical', 'deadline', 'due today', 'tomorrow', 'important', 'must', 'immediately'],
    'medium': ['meeting', 'call', 'review', 'submit', 'send', 'prepare', 'finish', 'complete'],
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
        for clause in re.split(r',\s+(?=[A-Z0-9])', line):
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


def _generate_schedule(tasks, start_hour=9):
    order = {'high': 0, 'medium': 1, 'low': 2}
    sorted_tasks = sorted(
        tasks,
        key=lambda t: (
            t.get('time') is not None,
            order.get(str(t.get('priority_key') or t.get('priority', 'medium')).lower(), 1),
        ),
    )
    schedule = []
    current = datetime.today().replace(hour=start_hour, minute=0, second=0, microsecond=0)

    for task in sorted_tasks:
        priority_key = str(task.get('priority_key') or task.get('priority', 'medium')).lower()
        if task.get('time'):
            hour, minute = [int(part) for part in task['time'].split(':')]
            current = current.replace(hour=hour, minute=minute)

        duration = int(task.get('duration_minutes') or task.get('duration') or 30)
        end = current + timedelta(minutes=duration)
        title = task.get('title') or task.get('task') or 'Untitled task'
        schedule.append({
            **task,
            'title': title,
            'task': title,
            'priority': priority_key.title(),
            'priority_key': priority_key,
            'time': current.strftime('%H:%M'),
            'start_time': current.strftime('%H:%M'),
            'end_time':   end.strftime('%H:%M'),
            'duration_minutes': duration,
            'duration': duration,
        })
        current = end + timedelta(minutes=10)
    return schedule


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

    tasks = _parse_raw_tasks(raw)
    request.session['parsed_tasks'] = tasks
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.parsed_tasks = tasks
    profile.save(update_fields=['parsed_tasks'])
    return JsonResponse({**_api_success({'tasks': tasks}), 'tasks': tasks})


@login_required
@require_POST
def upload_image(request):
    """POST /upload-image/  ->  { success, data: { extracted_text, tasks }, error }"""
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({**_api_error('No image uploaded.'), 'tasks': []}, status=400)

    extracted = _ocr_extract(image_file)
    tasks = _parse_raw_tasks(extracted)
    request.session['parsed_tasks'] = tasks
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.parsed_tasks = tasks
    profile.save(update_fields=['parsed_tasks'])
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
        tasks      = body.get('tasks') or request.session.get('parsed_tasks', []) or profile.parsed_tasks
        start_hour = int(body.get('start_hour', 9))
    except (json.JSONDecodeError, AttributeError, ValueError):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        tasks      = request.session.get('parsed_tasks', []) or profile.parsed_tasks
        start_hour = 9

    if not tasks:
        return JsonResponse({**_api_error('No tasks to schedule.'), 'schedule': []}, status=400)

    schedule = _generate_schedule(tasks, start_hour=start_hour)
    request.session['schedule'] = schedule
    request.session['parsed_tasks'] = tasks
    profile.parsed_tasks = tasks
    profile.schedule = schedule
    profile.save(update_fields=['parsed_tasks', 'schedule'])
    return JsonResponse({
        **_api_success({'schedule': schedule}),
        'schedule': schedule,
        'redirect': '/timeline/',
    })
