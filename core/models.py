from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, default='Curating a life of calm intention')
    avatar_data = models.TextField(blank=True)
    parsed_tasks = models.JSONField(default=list, blank=True)
    schedule = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f'{self.user.username} profile'
