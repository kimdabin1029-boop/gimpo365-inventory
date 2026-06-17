from django.urls import reverse
from django.views.generic import RedirectView


class HomeRedirectView(RedirectView):
    """루트(/) 진입 시 분기. (PRODUCT_SPEC §10.2)

    - 로그인 상태  → inventory 대시보드
    - 비로그인 상태 → 로그인 화면
    """

    def get_redirect_url(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            return reverse("inventory:dashboard")
        return reverse("accounts:login")
