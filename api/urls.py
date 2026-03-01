from django.urls import path
from . import views

urlpatterns = [
    path('reading/generate', views.generate_reading, name='generate_reading'),
]
