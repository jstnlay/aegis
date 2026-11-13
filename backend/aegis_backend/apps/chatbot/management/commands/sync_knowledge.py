"""
Load the assistant's knowledge corpus from the content the school already has.

The retriever answers from `KnowledgeDocument` rows, and this command is how
the existing content gets in: published Strapi announcements and resources,
plus the approved and active `cms.LearningItem` records. What an administrator
types by hand goes in through the admin screen instead.

The command is idempotent. Each document is keyed by its origin and the id of
the thing it came from, so running it again updates the existing document
rather than appending a second copy of the same announcement. With `--prune`,
a synced document whose source has disappeared is deactivated — never deleted,
because the passages a past reply cited have to keep resolving.

There is no scheduler in this project (see DECISIONS.md), so this runs from
the deployment's cron exactly like the other maintenance commands.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.chatbot.models import KnowledgeDocument
from apps.chatbot.retrieval import index_document


class Command(BaseCommand):
    help = "Sync the chatbot knowledge corpus from Strapi and approved learning items."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Deactivate synced documents whose source no longer exists.",
        )

    def handle(self, *args, **options):
        seen: set[tuple[str, str]] = set()
        created = updated = 0

        for rows in (self._strapi_rows(), self._learning_item_rows()):
            for row in rows:
                if self._upsert(seen, **row):
                    created += 1
                else:
                    updated += 1

        pruned = self._prune(seen) if options["prune"] else 0
        self.stdout.write(
            self.style.SUCCESS(
                f"Knowledge sync: {created} created, {updated} updated, "
                f"{pruned} deactivated."
            )
        )

    # -- sources ------------------------------------------------------------

    def _strapi_rows(self):
        from apps.cms.services.strapi_client import StrapiClient, StrapiError

        try:
            client = StrapiClient()
            announcements = client.list_announcements()
            resources = client.list_resources()
        except StrapiError as exc:
            # Strapi being down must not stop the local learning items from
            # syncing. A warning is the honest report; failing outright would
            # sync nothing at all.
            self.stderr.write(f"Strapi unavailable, skipping CMS content: {exc}")
            return

        for item in announcements:
            yield {
                "origin": KnowledgeDocument.Origin.STRAPI,
                "external_id": item["document_id"],
                "title": item["title"],
                "category": KnowledgeDocument.Category.ANNOUNCEMENT,
                # What the student sees cited. The title is enough: an
                # announcement has no page number.
                "source_label": item["title"],
                "body": item.get("content") or "",
            }
        for item in resources:
            yield {
                "origin": KnowledgeDocument.Origin.STRAPI,
                "external_id": item["document_id"],
                "title": item["title"],
                "category": KnowledgeDocument.Category.RESOURCE,
                "source_label": item["title"],
                "body": item.get("description") or "",
            }

    def _learning_item_rows(self):
        from apps.cms.models import LearningItem

        items = LearningItem.objects.filter(
            lifecycle_status=LearningItem.LifecycleStatus.APPROVED,
            is_active=True,
        )
        for item in items:
            yield {
                "origin": KnowledgeDocument.Origin.CMS,
                "external_id": f"learning-item:{item.pk}",
                "title": item.title,
                "category": KnowledgeDocument.Category.RESOURCE,
                "source_label": item.title,
                "body": "\n\n".join(
                    part for part in (item.title, item.topic, item.description) if part
                ),
            }

    # -- writes -------------------------------------------------------------

    @transaction.atomic
    def _upsert(self, seen, *, origin, external_id, title, category, source_label, body):
        """Create or update one document. Returns True when it was created."""
        seen.add((origin, external_id))
        document, created = KnowledgeDocument.objects.update_or_create(
            origin=origin,
            external_id=external_id,
            defaults={
                "title": title[:240],
                "category": category,
                "source_label": source_label[:120],
                "is_active": True,
            },
        )
        if body.strip():
            # Re-index every run. The source text is the authority, and a
            # document edited upstream must not stay retrievable in its old
            # wording.
            index_document(document, body)
        else:
            # Nothing to quote. Leaving the old passages behind would answer
            # from text the school has removed.
            document.chunks.all().delete()
        return created

    def _prune(self, seen: set[tuple[str, str]]) -> int:
        """Deactivate synced documents whose source is gone."""
        synced = KnowledgeDocument.objects.filter(
            origin__in=[
                KnowledgeDocument.Origin.STRAPI,
                KnowledgeDocument.Origin.CMS,
            ],
            is_active=True,
        )
        stale = [row for row in synced if (row.origin, row.external_id) not in seen]
        for row in stale:
            row.is_active = False
        KnowledgeDocument.objects.bulk_update(stale, ["is_active"])
        return len(stale)
