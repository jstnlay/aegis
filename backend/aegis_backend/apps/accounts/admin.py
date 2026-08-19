from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    User,
    StudentProfile,
    ParentProfile,
    ParentStudentLink,
    FacultyProfile,
    GuidanceProfile,
    AdminProfile,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "address", "profile_photo")}),
        ("Role", {"fields": ("role",)}),
        ("Privacy", {"fields": ("privacy_policy_accepted", "privacy_policy_accepted_at")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "student_id", "grade_level", "section", "is_active")
    search_fields = ("user__email", "student_id")


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "relationship_to_student")
    search_fields = ("user__email",)


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "is_primary")


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "department", "is_adviser")
    search_fields = ("user__email", "employee_id")


@admin.register(GuidanceProfile)
class GuidanceProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "specialization")
    search_fields = ("user__email", "employee_id")


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "admin_level")
    search_fields = ("user__email",)
