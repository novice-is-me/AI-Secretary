from django.db import models
from django.contrib.auth.models import User


class ScheduleSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    raw_input = models.TextField()
    input_image = models.ImageField(upload_to='uploads/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    schedule_date = models.DateField()
    is_reshuffled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.schedule_date}"


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    session = models.ForeignKey(ScheduleSession, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    duration_minutes = models.PositiveIntegerField(default=30)
    fixed_time = models.TimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    notes = models.TextField(blank=True)

    scheduled_start = models.TimeField(null=True, blank=True)
    scheduled_end = models.TimeField(null=True, blank=True)

    is_completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'scheduled_start']

    def __str__(self):
        return self.title
