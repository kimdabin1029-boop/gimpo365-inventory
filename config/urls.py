"""config root URL. (TECH_SPEC §13)"""

from django.contrib import admin
from django.urls import include, path

from core.views import HomeRedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", HomeRedirectView.as_view(), name="home"),
    path("accounts/", include("accounts.urls")),
    path("inventory/", include("inventory.urls")),
]
