"""
The assistant answers school questions from the school's own documents.

The client's complaint was that the chatbot is "not accurate". Half of that
was missing deterministic answers (tests_accuracy). The other half is that
for anything about the school itself — a rule, a policy, a schedule, a
procedure — it had nothing to quote, so it either said nothing or, with a
model available, said something plausible that was not this school's policy.

Retrieval fixes that: the reply is built from a passage of a document the
school published, and it names the document. These tests pin three
behaviours: a question that matches a document is answered from it and cited;
a question that matches nothing is refused rather than guessed at; and a
question about a student's own record never goes near retrieval, because a
record is a permission-checked lookup and a passage is prose anyone could
have typed.
"""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import StudentProfile
from apps.academics.models import AcademicYear, Enrollment, GradeLevel, Section
from apps.chatbot.agreements import notice_version
from apps.chatbot.models import (
    AgreementAcceptance,
    ChatMessage,
    KnowledgeChunk,
    KnowledgeDocument,
)
from apps.chatbot.retrieval import (
    chunk_text,
    excerpt,
    index_document,
    query_terms,
    retrieve,
)
from apps.cms.models import LearningItem
from apps.cms.services.strapi_client import StrapiError

User = get_user_model()


class ChunkingTest(TestCase):
    """A document becomes passages a student could be shown."""

    def test_short_paragraphs_are_packed_into_one_passage(self):
        # Packing keeps a passage large enough to be worth quoting; a document
        # of one-line paragraphs would otherwise retrieve as one-line chunks.
        chunks = chunk_text("First paragraph.\n\nSecond paragraph.")
        self.assertEqual(chunks, ["First paragraph.\n\nSecond paragraph."])

    def test_a_boundary_appears_when_the_passage_would_overflow(self):
        chunks = chunk_text(
            "First paragraph.\n\nSecond paragraph.", max_chars=30
        )
        self.assertEqual(chunks, ["First paragraph.", "Second paragraph."])

    def test_a_long_paragraph_is_split_on_sentence_ends(self):
        body = " ".join(f"Sentence number {index}." for index in range(60))
        chunks = chunk_text(body, max_chars=120)
        self.assertGreater(len(chunks), 1)
        # Never a half sentence: every passage ends where a sentence ends.
        for chunk in chunks:
            self.assertTrue(chunk.endswith("."))

    def test_whitespace_only_input_yields_no_passages(self):
        self.assertEqual(chunk_text("   \n\n  \t "), [])


class ExcerptTest(TestCase):
    """The cited window is readable and honest about being cut."""

    def test_short_text_is_returned_whole_without_an_ellipsis(self):
        self.assertEqual(excerpt("A short rule.", ["rule"]), "A short rule.")

    def test_a_long_text_is_windowed_around_the_query_terms(self):
        text = (
            ("Filler sentence here. " * 40)
            + "The late policy matters. "
            + ("More filler after. " * 40)
        )
        piece = excerpt(text, ["policy"], width=120)
        self.assertIn("policy", piece)
        self.assertTrue(piece.startswith("…"))
        self.assertTrue(piece.endswith("…"))


class QueryTermsTest(TestCase):
    """Terms a query is scored on: content words, folded, de-duplicated."""

    def test_stopwords_and_short_words_are_dropped(self):
        self.assertEqual(query_terms("What is the uniform policy?"),
                         ["uniform", "policy"])

    def test_a_plural_is_folded_onto_its_singular(self):
        self.assertIn("grade", query_terms("grades"))

    def test_repeats_are_dropped_but_order_is_kept(self):
        self.assertEqual(query_terms("policy uniform policy"), ["policy", "uniform"])


class RetrieveScoringTest(TestCase):
    """The scorer ranks real matches and refuses weak ones."""

    def make_document(self, title, body, **kwargs):
        document = KnowledgeDocument.objects.create(title=title, **kwargs)
        index_document(document, body)
        return document

    def test_a_question_matching_a_document_returns_that_document(self):
        document = self.make_document(
            "Student Handbook",
            "The school uniform policy requires a white polo every day.",
        )
        results = retrieve("What is the uniform policy?")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["document_id"], str(document.id))
        self.assertIn("uniform", results[0]["excerpt"].lower())

    def test_nothing_matching_returns_nothing(self):
        self.make_document("Student Handbook", "The uniform policy is strict.")
        self.assertEqual(retrieve("How do I join the chess club?"), [])

    def test_a_title_hit_carries_a_one_word_question(self):
        self.make_document("Uniform Policy", "Dress is checked each morning.")
        results = retrieve("uniform")
        self.assertEqual(len(results), 1)

    def test_one_matched_word_of_many_is_not_enough(self):
        # The document shares only "enrolment" with the query, and nothing in
        # its title. Quoting it would be a confident non-answer, so it is
        # refused instead.
        self.make_document("Notices", "The enrolment window is short.")
        self.assertEqual(retrieve("When is the enrolment deadline?"), [])

    def test_an_inactive_document_is_never_retrieved(self):
        document = self.make_document(
            "Retired Handbook", "The uniform policy is strict.", is_active=True
        )
        self.assertEqual(len(retrieve("uniform policy")), 1)
        document.is_active = False
        document.save(update_fields=["is_active"])
        self.assertEqual(retrieve("uniform policy"), [])

    def test_a_title_hit_outranks_a_body_hit(self):
        self.make_document("Uniform Policy", "General rules for everyone.")
        self.make_document(
            "Community Letter",
            "We discussed uniforms and the policy in passing last term.",
        )
        results = retrieve("uniform policy")
        self.assertEqual(results[0]["title"], "Uniform Policy")

    def test_reindexing_replaces_the_old_passages(self):
        long_body = " ".join(f"Old rule number {index}." for index in range(80))
        document = self.make_document("Handbook", long_body)
        self.assertGreater(
            KnowledgeChunk.objects.filter(document=document).count(), 1
        )
        index_document(document, "New rule about shoes only.")
        self.assertEqual(KnowledgeChunk.objects.filter(document=document).count(), 1)
        self.assertIn("New rule", document.chunks.get().content)


class RetrievalBase(TestCase):
    """A student who has accepted the notice, and no other data."""

    def setUp(self):
        self.client = APIClient()

        grade_level = GradeLevel.objects.create(name="Grade 7", level_number=7)
        academic_year = AcademicYear.objects.create(
            name="2024-2025",
            start_date=date(2024, 6, 10),
            end_date=date(2025, 3, 25),
            is_current=True,
        )
        section = Section.objects.create(
            name="Einstein", grade_level=grade_level, academic_year=academic_year
        )

        self.student_user = User.objects.create_user(
            email="rag_student@test.com",
            password="pass12345",
            first_name="Rita",
            last_name="Gomez",
            role="student",
        )
        student = StudentProfile.objects.create(
            user=self.student_user,
            student_id="RAG001",
            grade_level=grade_level,
            section=section,
            enrollment_date=date(2024, 6, 10),
        )
        Enrollment.objects.create(
            student=student,
            section=section,
            academic_year=academic_year,
            date_enrolled=date(2024, 6, 10),
            is_active=True,
        )
        AgreementAcceptance.objects.create(
            user=self.student_user,
            notice_version=notice_version(),
            accepted_at=date(2024, 6, 10),
        )

    def ask(self, message):
        self.client.force_authenticate(user=self.student_user)
        return self.client.post(
            "/api/v1/chatbot/message/", {"message": message}, format="json"
        )


class GroundedAnswerTest(RetrievalBase):
    """A question about the school is answered from the school's document."""

    def setUp(self):
        super().setUp()
        document = KnowledgeDocument.objects.create(
            title="Student Handbook",
            category=KnowledgeDocument.Category.HANDBOOK,
            source_label="Student Handbook 2026, p. 12",
        )
        index_document(
            document,
            "The school uniform policy requires a white polo shirt and black "
            "trousers every school day. Physical education days allow the PE "
            "uniform instead.",
        )

    def test_the_reply_quotes_the_document(self):
        resp = self.ask("What is the uniform policy?")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("white polo", resp.data["reply"].lower())

    def test_the_reply_names_the_source(self):
        resp = self.ask("What is the uniform policy?")
        self.assertIn("Student Handbook 2026, p. 12", resp.data["reply"])

    def test_the_passages_are_returned_to_the_client(self):
        resp = self.ask("What is the uniform policy?")
        passages = resp.data["data"]["knowledge"]
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["title"], "Student Handbook")

    def test_the_grounding_is_persisted_with_the_turn(self):
        self.ask("What is the uniform policy?")
        stored = ChatMessage.objects.get(user=self.student_user)
        self.assertEqual(len(stored.retrieved_sources), 1)
        self.assertEqual(stored.retrieved_sources[0]["title"], "Student Handbook")
        # Pointers, not a second copy of the passage.
        self.assertNotIn("content", stored.retrieved_sources[0])


class UngroundedAnswerTest(RetrievalBase):
    """A question the corpus does not cover is refused, not guessed at."""

    def test_a_school_question_with_no_document_is_refused(self):
        resp = self.ask("When is the quiz?")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("I don't have an answer for this one", resp.data["reply"])
        self.assertNotIn("knowledge", resp.data["data"])

    def test_the_refusal_still_names_what_it_can_do(self):
        resp = self.ask("When is the quiz?")
        self.assertIn("grades, attendance and approved learning resources",
                      resp.data["reply"])

    def test_nothing_is_persisted_when_nothing_was_retrieved(self):
        self.ask("When is the quiz?")
        stored = ChatMessage.objects.get(user=self.student_user)
        self.assertEqual(stored.retrieved_sources, [])


class RecordQuestionsBypassRetrievalTest(RetrievalBase):
    """A record question is answered from the record, never from a document."""

    def setUp(self):
        super().setUp()
        # A document that mentions grades a lot. The trap: if retrieval ran for
        # a grade question, this passage could be quoted as if it were the
        # student's own result.
        document = KnowledgeDocument.objects.create(
            title="Grading Policy",
            category=KnowledgeDocument.Category.POLICY,
        )
        index_document(
            document,
            "Grades are computed each quarter. A student's grade in a subject "
            "reflects their grade across assessments. Grades are final once "
            "posted.",
        )

    def test_a_grade_question_does_not_retrieve(self):
        resp = self.ask("What is my grade in Math?")
        self.assertEqual(resp.data["intent"], "ask_grade")
        self.assertNotIn("knowledge", resp.data["data"])

    def test_the_grade_answer_is_not_a_policy_passage(self):
        resp = self.ask("What is my grade in Math?")
        self.assertNotIn("Grading Policy", resp.data["reply"])
        self.assertNotIn("Grades are computed", resp.data["reply"])


class KnowledgeAdminApiTest(RetrievalBase):
    """Only an administrator manages the corpus, and editing it re-indexes."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            email="rag_admin@test.com",
            password="pass12345",
            first_name="Ada",
            last_name="Admin",
            role="admin",
        )
        self.url = "/api/v1/chatbot/admin/knowledge/"

    def post(self, payload, user=None):
        self.client.force_authenticate(user=user or self.admin)
        return self.client.post(self.url, payload, format="json")

    def test_an_administrator_creates_an_indexed_document(self):
        # Two paragraphs long enough that they cannot be packed into one
        # passage, so the chunk count is the count the text implies.
        paragraph = "The school uniform policy requires a white polo. " * 20
        resp = self.post(
            {
                "title": "Student Handbook",
                "category": "handbook",
                "source_label": "Handbook p. 3",
                "body": f"{paragraph}\n\n{paragraph}",
            }
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["chunk_count"], 2)
        self.assertEqual(KnowledgeChunk.objects.count(), 2)

    def test_a_document_without_text_is_refused(self):
        resp = self.post({"title": "Empty Handbook", "category": "handbook"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("body", resp.data["error"]["details"])

    def test_a_student_may_not_manage_the_corpus(self):
        resp = self.post(
            {"title": "Forged", "category": "policy", "body": "Anything."},
            user=self.student_user,
        )
        self.assertEqual(resp.status_code, 403)

    def test_editing_the_body_replaces_the_passages(self):
        document = KnowledgeDocument.objects.create(title="Handbook")
        index_document(document, "Old wording about shoes.")
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            f"{self.url}{document.id}/",
            {"body": "New wording about shoes."},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(document.chunks.count(), 1)
        self.assertIn("New wording", document.chunks.get().content)

    def test_editing_metadata_only_leaves_the_passages(self):
        document = KnowledgeDocument.objects.create(title="Handbook")
        index_document(document, "A rule that must survive the edit.")
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            f"{self.url}{document.id}/",
            {"title": "Renamed Handbook"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(document.chunks.count(), 1)

    def test_the_dashboard_reports_the_corpus_size(self):
        KnowledgeDocument.objects.create(title="Handbook")
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/chatbot/admin/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["knowledge"]["documents"], 1)
        # The document was created without text, so it is counted as unindexed.
        self.assertEqual(resp.data["knowledge"]["unindexed"], 1)


class SyncKnowledgeCommandTest(TestCase):
    """The sync pulls existing content in, once, and keeps it in step."""

    def setUp(self):
        self.learning_item = LearningItem.objects.create(
            item_type=LearningItem.ItemType.LEARNING_STRATEGY,
            title="Spaced Repetition",
            description="Study a little each day instead of all at once.",
            topic="Study skills",
            lifecycle_status=LearningItem.LifecycleStatus.APPROVED,
            is_active=True,
        )

    def run_sync(self, *args):
        # Strapi is unconfigured in tests; the command must still sync the
        # local learning items rather than fail on the network call.
        with patch(
            "apps.cms.services.strapi_client.StrapiClient",
            side_effect=StrapiError("offline in tests"),
        ):
            call_command("sync_knowledge", *args)

    def test_an_approved_learning_item_becomes_a_document(self):
        self.run_sync()
        document = KnowledgeDocument.objects.get(
            origin=KnowledgeDocument.Origin.CMS
        )
        self.assertEqual(document.title, "Spaced Repetition")
        self.assertGreater(document.chunks.count(), 0)

    def test_a_second_run_updates_rather_than_duplicates(self):
        self.run_sync()
        self.run_sync()
        self.assertEqual(KnowledgeDocument.objects.count(), 1)

    def test_a_draft_learning_item_is_not_synced(self):
        self.learning_item.lifecycle_status = LearningItem.LifecycleStatus.DRAFT
        self.learning_item.save(update_fields=["lifecycle_status"])
        self.run_sync()
        self.assertEqual(KnowledgeDocument.objects.count(), 0)

    def test_prune_deactivates_a_synced_document_whose_source_is_gone(self):
        stale = KnowledgeDocument.objects.create(
            title="Removed Announcement",
            origin=KnowledgeDocument.Origin.STRAPI,
            external_id="no-longer-in-strapi",
        )
        self.run_sync("--prune")
        stale.refresh_from_db()
        self.assertFalse(stale.is_active)

    def test_without_prune_a_stale_document_is_kept(self):
        stale = KnowledgeDocument.objects.create(
            title="Removed Announcement",
            origin=KnowledgeDocument.Origin.STRAPI,
            external_id="no-longer-in-strapi",
        )
        self.run_sync()
        stale.refresh_from_db()
        self.assertTrue(stale.is_active)
