"""
Recipient resolution for CMS announcements.

AEGIS Django users/roles remain the single source of truth. Strapi
never stores AEGIS identities — it only declares *targeting intent*
(target_roles / target_sections), which is resolved here against the
Django user base.

Section scoping ("where practical"):
  - students: matched via StudentProfile.section.name
  - parents:  matched via linked children's section
  - faculty/guidance/admin: school-wide staff, unaffected by the
    section filter (they serve all sections).
"""

from django.contrib.auth import get_user_model
from django.db.models import Q

STAFF_ROLES = ("faculty", "guidance", "admin")


def resolve_announcement_recipients(target_roles, target_sections):
    """
    Return the queryset of active AEGIS users targeted by an announcement.

    Args:
        target_roles: normalized list of role strings or ["all"].
        target_sections: normalized list of section names ([] = all).
    """
    User = get_user_model()

    qs = User.objects.filter(is_active=True)

    if "all" not in target_roles:
        qs = qs.filter(role__in=target_roles)

    if target_sections:
        member_q = Q(student_profile__section__name__in=target_sections) | Q(
            parent_profile__student_links__student__section__name__in=target_sections
        )
        staff_q = Q(role__in=STAFF_ROLES)
        qs = qs.filter(member_q | staff_q)

    return qs.distinct()
