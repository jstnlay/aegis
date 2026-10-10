from django.contrib import admin

from .models import PortfolioEntry


@admin.register(PortfolioEntry)
class PortfolioEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "activity_type", "created_at")
    list_filter = ("activity_type",)
    search_fields = ("title", "description")
