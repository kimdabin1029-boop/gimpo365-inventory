from django.db import models


class Department(models.Model):
    """부서. (TECH_SPEC §6.1)

    active_for_inventory=False 인 부서는 v0.1 재고관리 대상에서 제외된다.
    """

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    active_for_inventory = models.BooleanField(default=True)
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "부서"
        verbose_name_plural = "부서"

    def save(self, *args, **kwargs):
        # 저장 전 name strip 정규화 (TECH_SPEC §6.1)
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
