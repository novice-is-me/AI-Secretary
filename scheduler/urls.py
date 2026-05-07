from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('generate/', views.generate_schedule, name='generate_schedule'),
    path('task/<int:task_id>/toggle/', views.toggle_task, name='toggle_task'),
    path('reshuffle/<int:session_id>/', views.reshuffle, name='reshuffle'),
    path('auth/register/', views.register, name='register'),
]
