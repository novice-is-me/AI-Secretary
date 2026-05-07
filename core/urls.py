from django.urls import path
from . import views

urlpatterns = [
    # Landing
    path('', views.home, name='home'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),

    # App pages (login required)
    path('huddle/', views.huddle_view, name='huddle'),
    path('timeline/', views.timeline_view, name='timeline'),
    path('profile/', views.profile_view, name='profile'),

    # API endpoints
    path('chat/', views.chat_view, name='chat'),
    path('parse-text/', views.parse_text, name='parse_text'),
    path('upload-image/', views.upload_image, name='upload_image'),
    path('generate-schedule/', views.generate_schedule, name='generate_schedule'),
    path('delete-task/', views.delete_task, name='delete_task'),
]
