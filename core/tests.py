import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import UserProfile


class AuthFlowTests(TestCase):
    def test_login_success_redirects_to_huddle_and_logout_returns_home(self):
        User.objects.create_user(
            username='kurt@example.com',
            email='kurt@example.com',
            password='testpass123',
        )

        response = self.client.post(reverse('login'), {
            'email': 'kurt@example.com',
            'password': 'testpass123',
        })
        self.assertRedirects(response, reverse('huddle'))

        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "localStorage.removeItem('sanctuary_huddle_messages')")
        self.assertContains(response, "localStorage.setItem('sanctuary_huddle_history_visible', 'false')")
        self.assertContains(response, reverse('home'))

    def test_login_email_is_case_insensitive(self):
        User.objects.create_user(
            username='kurt@example.com',
            email='kurt@example.com',
            password='testpass123',
        )

        response = self.client.post(reverse('login'), {
            'email': 'KURT@EXAMPLE.COM',
            'password': 'testpass123',
        })

        self.assertRedirects(response, reverse('huddle'))

    def test_authenticated_user_can_open_register_page_for_account_switching(self):
        user = User.objects.create_user(
            username='logged-in@example.com',
            email='logged-in@example.com',
            password='testpass123',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Account')


class MockAIPipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='demo@example.com',
            email='demo@example.com',
            password='testpass123',
        )
        self.client.force_login(self.user)

    def test_parse_text_returns_success_data_and_template_compatible_tasks(self):
        response = self.client.post(
            reverse('parse_text'),
            data=json.dumps({'text': 'Study Django tomorrow for 2 hours, Meeting at 3pm\nRead docs for 20 min'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIsNone(payload['error'])
        self.assertEqual(len(payload['data']['tasks']), 3)

        first = payload['data']['tasks'][0]
        self.assertEqual(first['task'], 'Study Django')
        self.assertEqual(first['duration'], 120)
        self.assertEqual(first['priority'], 'Medium')
        self.assertEqual(first['priority_key'], 'medium')

        second = payload['data']['tasks'][1]
        self.assertEqual(second['task'], 'Meeting')
        self.assertEqual(second['time'], '15:00')
        self.assertEqual(second['priority_key'], 'high')

        third = payload['data']['tasks'][2]
        self.assertEqual(third['task'], 'Read docs')
        self.assertEqual(third['duration'], 20)

    def test_generate_schedule_uses_parsed_tasks_and_stores_session_schedule(self):
        self.client.post(
            reverse('parse_text'),
            data=json.dumps({'text': 'Study Django tomorrow for 2 hours, Meeting at 3pm'}),
            content_type='application/json',
        )

        response = self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({'start_hour': 9}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['schedule'][0]['time'], '09:00')
        self.assertEqual(payload['data']['schedule'][0]['task'], 'Study Django')
        self.assertEqual(payload['data']['schedule'][1]['time'], '15:00')
        self.assertEqual(payload['data']['schedule'][1]['task'], 'Meeting')
        self.assertEqual(payload['redirect'], '/timeline/')

    def test_generated_schedule_persists_to_logged_in_profile(self):
        self.client.post(
            reverse('parse_text'),
            data=json.dumps({'text': 'Study Django tomorrow for 2 hours, Meeting at 3pm'}),
            content_type='application/json',
        )
        self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({'start_hour': 9}),
            content_type='application/json',
        )

        self.user.profile.refresh_from_db()
        self.assertEqual(len(self.user.profile.parsed_tasks), 2)
        self.assertEqual(len(self.user.profile.schedule), 2)
        self.assertEqual(self.user.profile.schedule[0]['task'], 'Study Django')

    def test_comma_separated_lowercase_tasks_are_split(self):
        response = self.client.post(
            reverse('parse_text'),
            data=json.dumps({'text': 'study django for 30 minutes, meeting at 3pm, read docs'}),
            content_type='application/json',
        )

        tasks = response.json()['data']['tasks']
        self.assertEqual([task['task'] for task in tasks], ['study django', 'meeting', 'read docs'])
        self.assertEqual(tasks[0]['priority_key'], 'medium')
        self.assertEqual(tasks[1]['priority_key'], 'high')

    def test_schedule_dates_are_preserved_separately(self):
        today = timezone.localdate().isoformat()
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

        first = self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({
                'schedule_date': today,
                'tasks': [{'id': 1, 'title': 'Today task', 'task': 'Today task', 'duration': 30, 'priority_key': 'medium', 'schedule_date': today}],
            }),
            content_type='application/json',
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({
                'schedule_date': tomorrow,
                'tasks': [
                    {'id': 1, 'title': 'Today task', 'task': 'Today task', 'duration': 30, 'priority_key': 'medium', 'schedule_date': today},
                    {'id': 2, 'title': 'Tomorrow task', 'task': 'Tomorrow task', 'duration': 30, 'priority_key': 'medium', 'schedule_date': tomorrow},
                ],
            }),
            content_type='application/json',
        )

        schedule = second.json()['schedule']
        self.assertEqual({item['schedule_date'] for item in schedule}, {today, tomorrow})

    def test_auto_task_uses_next_open_slot_without_overwriting_existing_schedule(self):
        today = timezone.localdate().isoformat()
        first_tasks = [
            {'id': 1, 'title': 'First auto', 'task': 'First auto', 'duration': 30, 'priority_key': 'medium', 'schedule_date': today},
        ]
        self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({'schedule_date': today, 'tasks': first_tasks}),
            content_type='application/json',
        )
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.parsed_tasks[0]['time'], '09:00')

        second_tasks = self.user.profile.parsed_tasks + [
            {'id': 2, 'title': 'Second auto', 'task': 'Second auto', 'duration': 30, 'priority_key': 'medium', 'time': None, 'schedule_date': today},
        ]
        response = self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({'schedule_date': today, 'tasks': second_tasks}),
            content_type='application/json',
        )

        schedule = response.json()['schedule']
        first = next(item for item in schedule if item['task'] == 'First auto')
        second = next(item for item in schedule if item['task'] == 'Second auto')
        self.assertEqual(first['start_time'], '09:00')
        self.assertEqual(second['start_time'], '09:40')

    def test_huddle_parse_then_generate_appends_auto_task_to_existing_day(self):
        today = timezone.localdate().isoformat()
        self.client.post(
            reverse('parse_text'),
            data=json.dumps({'text': 'First auto for 30 minutes', 'schedule_date': today}),
            content_type='application/json',
        )
        self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({
                'schedule_date': today,
                'tasks': [{'id': 1, 'title': 'First auto', 'task': 'First auto', 'duration': 30, 'priority_key': 'medium', 'schedule_date': today}],
            }),
            content_type='application/json',
        )

        self.client.post(
            reverse('parse_text'),
            data=json.dumps({'text': 'Second auto for 30 minutes', 'schedule_date': today}),
            content_type='application/json',
        )
        response = self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({
                'schedule_date': today,
                'tasks': [{'id': 1, 'title': 'Second auto', 'task': 'Second auto', 'duration': 30, 'priority_key': 'medium', 'schedule_date': today}],
            }),
            content_type='application/json',
        )

        schedule = response.json()['schedule']
        first = next(item for item in schedule if item['task'] == 'First auto')
        second = next(item for item in schedule if item['task'] == 'Second auto')
        self.assertEqual(first['start_time'], '09:00')
        self.assertEqual(second['start_time'], '09:40')

    def test_reshuffle_clears_selected_day_pinned_times_only(self):
        today = timezone.localdate().isoformat()
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        tasks = [
            {'id': 1, 'title': 'Today pinned', 'task': 'Today pinned', 'duration': 30, 'priority_key': 'medium', 'time': '15:00', 'schedule_date': today},
            {'id': 2, 'title': 'Tomorrow pinned', 'task': 'Tomorrow pinned', 'duration': 30, 'priority_key': 'medium', 'time': '16:00', 'schedule_date': tomorrow},
        ]
        self.client.post(reverse('generate_schedule'), data=json.dumps({'tasks': tasks, 'schedule_date': today}), content_type='application/json')
        self.client.post(reverse('generate_schedule'), data=json.dumps({'tasks': tasks, 'schedule_date': tomorrow}), content_type='application/json')

        response = self.client.post(
            reverse('generate_schedule'),
            data=json.dumps({'tasks': tasks, 'schedule_date': today, 'reshuffle': True}),
            content_type='application/json',
        )

        schedule = response.json()['schedule']
        today_item = next(item for item in schedule if item['task'] == 'Today pinned')
        tomorrow_item = next(item for item in schedule if item['task'] == 'Tomorrow pinned')
        self.assertEqual(today_item['start_time'], '09:00')
        self.assertEqual(tomorrow_item['start_time'], '16:00')

    def test_delete_task_removes_task_and_schedule_item_for_date(self):
        today = timezone.localdate().isoformat()
        tasks = [{'id': 1, 'title': 'Delete me', 'task': 'Delete me', 'duration': 30, 'priority_key': 'medium', 'schedule_date': today}]
        self.client.post(reverse('generate_schedule'), data=json.dumps({'tasks': tasks, 'schedule_date': today}), content_type='application/json')

        response = self.client.post(
            reverse('delete_task'),
            data=json.dumps({'id': 1, 'title': 'Delete me', 'schedule_date': today}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.parsed_tasks, [])
        self.assertEqual(self.user.profile.schedule, [])

    def test_huddle_and_timeline_render_logged_in_user_name(self):
        self.user.first_name = 'Demo'
        self.user.last_name = 'User'
        self.user.save()
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.schedule = [{'start_time': '09:00', 'end_time': '09:30', 'title': 'Plan demo', 'task': 'Plan demo', 'duration_minutes': 30, 'priority_key': 'medium'}]
        profile.save()

        huddle_response = self.client.get(reverse('huddle'))
        timeline_response = self.client.get(reverse('timeline'))

        self.assertContains(huddle_response, 'Demo User')
        self.assertContains(timeline_response, 'Demo User')
        self.assertContains(timeline_response, 'Plan demo')


class ProfileTests(TestCase):
    def test_profile_page_uses_logged_in_user_data(self):
        user = User.objects.create_user(
            username='profile@example.com',
            email='profile@example.com',
            password='testpass123',
            first_name='Kurt',
            last_name='Lim',
        )
        UserProfile.objects.create(user=user, bio='Demo builder')
        self.client.force_login(user)

        response = self.client.get(reverse('profile'))

        self.assertContains(response, 'Kurt Lim')
        self.assertContains(response, 'profile@example.com')
        self.assertContains(response, 'Demo builder')

    def test_profile_save_updates_only_logged_in_account(self):
        user = User.objects.create_user(
            username='profile@example.com',
            email='profile@example.com',
            password='testpass123',
        )
        other = User.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            password='testpass123',
        )
        self.client.force_login(user)

        response = self.client.post(reverse('profile'), {
            'full_name': 'Updated User',
            'bio': 'Saved per account',
            'email': 'updated@example.com',
            'avatar_data': 'data:image/png;base64,demo',
        })

        self.assertRedirects(response, reverse('profile'))
        user.refresh_from_db()
        other.refresh_from_db()
        profile = user.profile

        self.assertEqual(user.first_name, 'Updated')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.email, 'updated@example.com')
        self.assertEqual(user.username, 'updated@example.com')
        self.assertEqual(profile.bio, 'Saved per account')
        self.assertEqual(profile.avatar_data, 'data:image/png;base64,demo')
        self.assertEqual(other.email, 'other@example.com')
