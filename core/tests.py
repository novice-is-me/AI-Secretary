import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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
        self.assertContains(response, "localStorage.removeItem('sanctuary_huddle_messages')")
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
        self.assertEqual(first['priority'], 'High')
        self.assertEqual(first['priority_key'], 'high')

        second = payload['data']['tasks'][1]
        self.assertEqual(second['task'], 'Meeting')
        self.assertEqual(second['time'], '15:00')

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
