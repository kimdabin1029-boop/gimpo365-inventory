"""accounts URL: 로그인 / 로그아웃. (TECH_SPEC §13)"""

from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
]
