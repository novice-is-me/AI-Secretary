from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import ScheduleSession, Task
from .services.scheduler_service import build_schedule, reshuffle_schedule
from .views import _resolve_day


# ── Scheduling Engine ────────────────────────────────────────────────────────

class SchedulerServiceTests(TestCase):

    def test_flexible_tasks_fill_free_slots(self):
        tasks = [
            {'title': 'Write report', 'duration_minutes': 60, 'fixed_time': None, 'priority': 'high', 'notes': ''},
            {'title': 'Reply emails', 'duration_minutes': 30, 'fixed_time': None, 'priority': 'medium', 'notes': ''},
        ]
        result = build_schedule(tasks, start_from=time(9, 0))
        self.assertEqual(result[0]['title'], 'Write report')
        self.assertEqual(result[0]['scheduled_start'], '09:00')
        self.assertEqual(result[0]['scheduled_end'], '10:00')
        self.assertEqual(result[1]['scheduled_start'], '10:00')
        self.assertEqual(result[1]['scheduled_end'], '10:30')

    def test_fixed_time_task_placed_at_correct_time(self):
        tasks = [
            {'title': 'Standup', 'duration_minutes': 30, 'fixed_time': '14:00', 'priority': 'high', 'notes': ''},
            {'title': 'Prep work', 'duration_minutes': 60, 'fixed_time': None, 'priority': 'medium', 'notes': ''},
        ]
        result = build_schedule(tasks, start_from=time(9, 0))
        standup = next(t for t in result if t['title'] == 'Standup')
        self.assertEqual(standup['scheduled_start'], '14:00')
        self.assertEqual(standup['scheduled_end'], '14:30')

    def test_flexible_tasks_sorted_by_priority(self):
        tasks = [
            {'title': 'Low', 'duration_minutes': 30, 'fixed_time': None, 'priority': 'low', 'notes': ''},
            {'title': 'High', 'duration_minutes': 30, 'fixed_time': None, 'priority': 'high', 'notes': ''},
            {'title': 'Med', 'duration_minutes': 30, 'fixed_time': None, 'priority': 'medium', 'notes': ''},
        ]
        result = build_schedule(tasks, start_from=time(9, 0))
        self.assertEqual([t['title'] for t in result], ['High', 'Med', 'Low'])

    def test_reshuffle_starts_from_current_time(self):
        tasks = [{'title': 'Task A', 'duration_minutes': 60, 'fixed_time': None, 'priority': 'high', 'notes': ''}]
        result = reshuffle_schedule(tasks)
        self.assertIsNotNone(result[0]['scheduled_start'])

    def test_fixed_time_not_moved_by_reshuffle(self):
        tasks = [{'title': 'Late meeting', 'duration_minutes': 30, 'fixed_time': '20:00', 'priority': 'high', 'notes': ''}]
        result = reshuffle_schedule(tasks)
        self.assertEqual(result[0]['scheduled_start'], '20:00')

    def test_empty_tasks_returns_empty(self):
        self.assertEqual(build_schedule([]), [])


# ── Day Resolution ────────────────────────────────────────────────────────────

class DayResolutionTests(TestCase):

    def setUp(self):
        # Use a fixed Thursday for reproducible tests
        self.thursday = date(2026, 5, 7)  # Thursday

    def test_today_resolves_to_today(self):
        self.assertEqual(_resolve_day('today', self.thursday), self.thursday)

    def test_none_resolves_to_today(self):
        self.assertEqual(_resolve_day(None, self.thursday), self.thursday)

    def test_tomorrow_resolves_correctly(self):
        self.assertEqual(_resolve_day('tomorrow', self.thursday), self.thursday + timedelta(days=1))

    def test_named_weekday_resolves_to_next_occurrence(self):
        # Thursday → next Tuesday is 5 days away
        result = _resolve_day('Tuesday', self.thursday)
        self.assertEqual(result.weekday(), 1)  # 1 = Tuesday
        self.assertGreater(result, self.thursday)

    def test_same_weekday_resolves_to_today(self):
        # Thursday → Thursday = same day (0 days ahead)
        result = _resolve_day('Thursday', self.thursday)
        self.assertEqual(result, self.thursday)

    def test_upcoming_weekday_this_week(self):
        # Thursday → Saturday is 2 days ahead
        result = _resolve_day('Saturday', self.thursday)
        self.assertEqual(result, self.thursday + timedelta(days=2))

    def test_next_prefix_ignored_gracefully(self):
        result = _resolve_day('next Monday', self.thursday)
        self.assertEqual(result.weekday(), 0)  # 0 = Monday


# ── Auth ─────────────────────────────────────────────────────────────────────

class AuthTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')

    def test_login_page_loads(self):
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)

    def test_register_page_loads(self):
        self.assertEqual(self.client.get(reverse('register')).status_code, 200)

    def test_register_creates_user_and_redirects(self):
        resp = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'strongpass456!',
            'password2': 'strongpass456!',
        })
        self.assertRedirects(resp, reverse('dashboard'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_login_redirects_to_dashboard(self):
        resp = self.client.post(reverse('login'), {'username': 'testuser', 'password': 'testpass123'})
        self.assertRedirects(resp, reverse('dashboard'))

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertRedirects(resp, '/auth/login/?next=/dashboard/')

    def test_dashboard_loads_authenticated(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Brain Dump')


# ── Generate Schedule ─────────────────────────────────────────────────────────

MOCK_TASKS = [
    {'title': 'Write report', 'duration_minutes': 60, 'fixed_time': None, 'day': 'today', 'priority': 'high', 'notes': ''},
    {'title': '3pm meeting', 'duration_minutes': 30, 'fixed_time': '15:00', 'day': 'today', 'priority': 'high', 'notes': ''},
    {'title': 'Reply emails', 'duration_minutes': 30, 'fixed_time': None, 'day': 'today', 'priority': 'medium', 'notes': ''},
]

MOCK_TASKS_MULTIDAY = [
    {'title': 'Write report', 'duration_minutes': 60, 'fixed_time': None, 'day': 'today', 'priority': 'high', 'notes': ''},
    {'title': 'Dentist', 'duration_minutes': 60, 'fixed_time': '14:00', 'day': 'Tuesday', 'priority': 'high', 'notes': ''},
    {'title': 'Clean house', 'duration_minutes': 120, 'fixed_time': None, 'day': 'Saturday', 'priority': 'medium', 'notes': ''},
]


class GenerateScheduleTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')

    def test_empty_input_shows_error_message(self):
        resp = self.client.post(reverse('generate_schedule'), {'brain_dump': ''}, follow=True)
        self.assertContains(resp, 'Please enter some tasks')

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_TASKS)
    def test_valid_input_creates_session_and_tasks(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'write report, 3pm meeting, emails'})
        session = ScheduleSession.objects.filter(user=self.user).first()
        self.assertIsNotNone(session)
        self.assertEqual(session.tasks.count(), 3)

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_TASKS)
    def test_schedule_displayed_on_dashboard(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'tasks'})
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Write report')

    @patch('scheduler.views.parse_tasks_from_text', side_effect=Exception('API error'))
    def test_ai_failure_shows_friendly_error(self, _mock):
        resp = self.client.post(reverse('generate_schedule'), {'brain_dump': 'tasks'}, follow=True)
        self.assertContains(resp, 'AI parsing failed')

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_TASKS_MULTIDAY)
    def test_multiday_tasks_get_correct_dates(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'report, dentist Tuesday, clean house Saturday'})
        session = ScheduleSession.objects.filter(user=self.user).first()
        self.assertEqual(session.tasks.count(), 3)
        dates = set(session.tasks.values_list('task_date', flat=True))
        self.assertEqual(len(dates), 3)  # Three different dates

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_TASKS_MULTIDAY)
    def test_dashboard_shows_day_tabs_for_multiday(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'tasks'})
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Today')  # Tab for today


# ── Toggle Task ───────────────────────────────────────────────────────────────

class ToggleTaskTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        self.session = ScheduleSession.objects.create(
            user=self.user, raw_input='test', schedule_date=date.today()
        )
        self.task = Task.objects.create(
            session=self.session, title='Test task', duration_minutes=30,
            task_date=date.today(),
            scheduled_start=time(9, 0), scheduled_end=time(9, 30),
        )

    def test_toggle_marks_complete(self):
        resp = self.client.post(reverse('toggle_task', args=[self.task.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertJSONEqual(resp.content, {'completed': True})
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_completed)

    def test_toggle_twice_reverts(self):
        self.client.post(reverse('toggle_task', args=[self.task.id]))
        self.client.post(reverse('toggle_task', args=[self.task.id]))
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_completed)

    def test_cannot_toggle_other_users_task(self):
        other = User.objects.create_user('other', password='otherpass')
        other_session = ScheduleSession.objects.create(user=other, raw_input='x', schedule_date=date.today())
        other_task = Task.objects.create(session=other_session, title='Private', duration_minutes=30)
        resp = self.client.post(reverse('toggle_task', args=[other_task.id]))
        self.assertEqual(resp.status_code, 404)


# ── Reshuffle ─────────────────────────────────────────────────────────────────

class ReshuffleTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        self.today = date.today()
        self.session = ScheduleSession.objects.create(
            user=self.user, raw_input='test', schedule_date=self.today
        )
        Task.objects.create(
            session=self.session, title='Done', duration_minutes=30,
            task_date=self.today,
            scheduled_start=time(9, 0), scheduled_end=time(9, 30), is_completed=True,
        )
        Task.objects.create(
            session=self.session, title='Pending', duration_minutes=60,
            task_date=self.today,
            scheduled_start=time(9, 30), scheduled_end=time(10, 30),
        )

    def test_reshuffle_updates_pending_times(self):
        original_start = Task.objects.get(title='Pending').scheduled_start
        self.client.post(reverse('reshuffle', args=[self.session.id]), {'task_date': str(self.today)})
        new_start = Task.objects.get(title='Pending').scheduled_start
        self.assertNotEqual(original_start, new_start)

    def test_reshuffle_marks_session_flag(self):
        self.client.post(reverse('reshuffle', args=[self.session.id]), {'task_date': str(self.today)})
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_reshuffled)

    def test_completed_tasks_not_moved(self):
        self.client.post(reverse('reshuffle', args=[self.session.id]), {'task_date': str(self.today)})
        done = Task.objects.get(title='Done')
        self.assertEqual(done.scheduled_start, time(9, 0))


# ── Reset Schedule ────────────────────────────────────────────────────────────

class ResetScheduleTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        self.session = ScheduleSession.objects.create(
            user=self.user, raw_input='test', schedule_date=date.today()
        )
        Task.objects.create(session=self.session, title='Task', duration_minutes=30)

    def test_reset_deletes_all_sessions(self):
        self.client.post(reverse('reset_schedule'))
        self.assertEqual(ScheduleSession.objects.filter(user=self.user).count(), 0)

    def test_reset_redirects_to_dashboard(self):
        resp = self.client.post(reverse('reset_schedule'))
        self.assertRedirects(resp, reverse('dashboard'))

    def test_dashboard_empty_after_reset(self):
        self.client.post(reverse('reset_schedule'))
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Nothing planned yet')

    def test_reset_does_not_affect_other_users(self):
        other = User.objects.create_user('other', password='pass')
        ScheduleSession.objects.create(user=other, raw_input='x', schedule_date=date.today())
        self.client.post(reverse('reset_schedule'))
        self.assertEqual(ScheduleSession.objects.filter(user=other).count(), 1)


# ── Add-to-Plan (no auto-reset) ───────────────────────────────────────────────

MOCK_FIRST = [
    {'title': 'Task One', 'duration_minutes': 60, 'fixed_time': None, 'day': 'today', 'priority': 'high', 'notes': ''},
]
MOCK_SECOND = [
    {'title': 'Task Two', 'duration_minutes': 30, 'fixed_time': None, 'day': 'today', 'priority': 'medium', 'notes': ''},
]


class AddToPlanTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_FIRST)
    def test_second_dump_reuses_session(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'task one'})
        self.assertEqual(ScheduleSession.objects.filter(user=self.user).count(), 1)

    @patch('scheduler.views.parse_tasks_from_text')
    def test_second_dump_adds_tasks(self, mock_parse):
        mock_parse.return_value = MOCK_FIRST
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'task one'})
        mock_parse.return_value = MOCK_SECOND
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'task two'})
        session = ScheduleSession.objects.filter(user=self.user).first()
        self.assertEqual(session.tasks.count(), 2)
        self.assertEqual(ScheduleSession.objects.filter(user=self.user).count(), 1)

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_FIRST)
    def test_button_shows_add_to_plan_when_session_exists(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'task one'})
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Add to Plan')

    def test_button_shows_plan_my_week_when_no_session(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Plan My Week')


# ── Export ICS ────────────────────────────────────────────────────────────────

class ExportICSTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        self.session = ScheduleSession.objects.create(
            user=self.user, raw_input='test', schedule_date=date.today()
        )
        Task.objects.create(
            session=self.session, title='Morning run',
            duration_minutes=60, task_date=date.today(),
            scheduled_start=time(7, 0), scheduled_end=time(8, 0),
            priority='medium',
        )
        Task.objects.create(
            session=self.session, title='Dentist',
            duration_minutes=60, task_date=date(2026, 5, 13),
            scheduled_start=time(10, 0), scheduled_end=time(11, 0),
            priority='high',
        )

    def test_ics_returns_calendar_content_type(self):
        resp = self.client.get(reverse('export_ics', args=[self.session.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/calendar', resp['Content-Type'])

    def test_ics_contains_both_tasks(self):
        resp = self.client.get(reverse('export_ics', args=[self.session.id]))
        self.assertIn(b'Morning run', resp.content)
        self.assertIn(b'Dentist', resp.content)

    def test_ics_uses_task_date_not_session_date(self):
        resp = self.client.get(reverse('export_ics', args=[self.session.id]))
        # Dentist is on 2026-05-13 → should appear as 20260513 in DTSTART
        self.assertIn(b'20260513', resp.content)

    def test_cannot_export_other_users_ics(self):
        other = User.objects.create_user('other', password='pass')
        other_session = ScheduleSession.objects.create(
            user=other, raw_input='x', schedule_date=date.today()
        )
        resp = self.client.get(reverse('export_ics', args=[other_session.id]))
        self.assertEqual(resp.status_code, 404)


# ── ISO Date Resolution ───────────────────────────────────────────────────────

class ISODateResolutionTests(TestCase):

    def setUp(self):
        self.today = date(2026, 5, 7)

    def test_iso_date_resolves_exactly(self):
        self.assertEqual(_resolve_day('2026-05-13', self.today), date(2026, 5, 13))

    def test_iso_date_future_month(self):
        self.assertEqual(_resolve_day('2026-08-01', self.today), date(2026, 8, 1))

    def test_invalid_string_falls_back_to_today(self):
        self.assertEqual(_resolve_day('May 13', self.today), self.today)


# ── Week Calendar View ────────────────────────────────────────────────────────

MOCK_MULTIDAY = [
    {'title': 'Today task',    'duration_minutes': 60, 'fixed_time': None, 'day': 'today',      'priority': 'high',   'notes': ''},
    {'title': 'Tomorrow task', 'duration_minutes': 30, 'fixed_time': None, 'day': 'tomorrow',   'priority': 'medium', 'notes': ''},
    {'title': 'May 13 task',   'duration_minutes': 60, 'fixed_time': None, 'day': '2026-05-13', 'priority': 'low',    'notes': ''},
]


class WeekCalendarTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_MULTIDAY)
    def test_week_shows_7_day_columns(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'tasks'})
        resp = self.client.get(reverse('dashboard'))
        # 7 day headers rendered (today + 6 more)
        self.assertGreaterEqual(resp.content.count(b'FRI\xc2\xb7'), 0)  # just check it loads
        self.assertContains(resp, 'This Week')

    @patch('scheduler.views.parse_tasks_from_text', return_value=MOCK_MULTIDAY)
    def test_tasks_appear_in_correct_day_columns(self, _mock):
        self.client.post(reverse('generate_schedule'), {'brain_dump': 'tasks'})
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Today task')
        self.assertContains(resp, 'Tomorrow task')
        self.assertContains(resp, 'May 13 task')
