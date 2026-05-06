from django.urls import path
from . import views

urlpatterns = [
  path('parse-text/', views.parse_text, name='parse_text'),
  path('upload-image/', views.upload_image, name='upload_image'),
  path('generate-schedule/', views.generate_schedule, name='generate_schedule'),
]