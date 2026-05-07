from datetime import date, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import ScheduleSession, Task
from .services.scheduler_service import build_schedule, reshuffle_schedule


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
    {'title': 'Write report', 'duration_minutes': 60, 'fixed_time': None, 'priority': 'high', 'notes': ''},
    {'title': '3pm meeting', 'duration_minutes': 30, 'fixed_time': '15:00', 'priority': 'high', 'notes': ''},
    {'title': 'Reply emails', 'duration_minutes': 30, 'fixed_time': None, 'priority': 'medium', 'notes': ''},
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
        self.assertContains(resp, 'Your Daily Roadmap')

    @patch('scheduler.views.parse_tasks_from_text', side_effect=Exception('API error'))
    def test_ai_failure_shows_friendly_error(self, _mock):
        resp = self.client.post(reverse('generate_schedule'), {'brain_dump': 'tasks'}, follow=True)
        self.assertContains(resp, 'AI parsing failed')


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
        self.session = ScheduleSession.objects.create(
            user=self.user, raw_input='test', schedule_date=date.today()
        )
        Task.objects.create(
            session=self.session, title='Done', duration_minutes=30,
            scheduled_start=time(9, 0), scheduled_end=time(9, 30), is_completed=True,
        )
        Task.objects.create(
            session=self.session, title='Pending', duration_minutes=60,
            scheduled_start=time(9, 30), scheduled_end=time(10, 30),
        )

    def test_reshuffle_updates_pending_times(self):
        original_start = Task.objects.get(title='Pending').scheduled_start
        self.client.post(reverse('reshuffle', args=[self.session.id]))
        new_start = Task.objects.get(title='Pending').scheduled_start
        self.assertNotEqual(original_start, new_start)

    def test_reshuffle_marks_session_flag(self):
        self.client.post(reverse('reshuffle', args=[self.session.id]))
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_reshuffled)

    def test_completed_tasks_not_moved(self):
        self.client.post(reverse('reshuffle', args=[self.session.id]))
        done = Task.objects.get(title='Done')
        self.assertEqual(done.scheduled_start, time(9, 0))
