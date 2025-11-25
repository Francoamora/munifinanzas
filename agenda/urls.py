# agenda/urls.py
from django.urls import path
from .views import (
    AgendaListView,
    AgendaCreateView,
    AgendaDetailView,
    AgendaUpdateView,
    AgendaMarcarCompletadaView,
)

app_name = "agenda"

urlpatterns = [
    path("", AgendaListView.as_view(), name="agenda_list"),
    path("nueva/", AgendaCreateView.as_view(), name="agenda_create"),
    path("<int:pk>/", AgendaDetailView.as_view(), name="agenda_detail"),
    path("<int:pk>/editar/", AgendaUpdateView.as_view(), name="agenda_update"),
    path("<int:pk>/completar/", AgendaMarcarCompletadaView.as_view(), name="agenda_completar"),
]

