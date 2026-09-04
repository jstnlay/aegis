"""
AEGIS AI Engine — Recommender.

PH9 D16: Collaborative Filtering + content-based fallback.
PH9 D18: Initial CF = item-item + cosine similarity.
PH9 D19: Baseline thresholds.

CF interaction = observable student interaction with a learning item
(viewed, started, completed, saved/accepted).

IMPORTANT:
  - Grades are NOT CF preference signals.
  - Attendance is NOT CF preference signals.
  - Behavior is NOT CF preference signals.
  - Counseling is NOT CF preference signals.

Content-based is the fallback for:
  - new students
  - sparse interaction history
  - insufficient overall interaction density
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ai_engine.config import (
    CF_MIN_DISTINCT_ITEMS_PER_STUDENT,
    CF_MIN_INTERACTIONS_PER_STUDENT,
    CF_MIN_STUDENTS_PER_ITEM,
)

logger = logging.getLogger(__name__)


class InteractionMatrix:
    """
    Build a student × item interaction matrix from StudentInteraction records.

    Values are weighted by interaction type:
      viewed   = 1
      started  = 2
      saved    = 3
      completed = 4
    """

    INTERACTION_WEIGHTS = {
        "viewed": 1.0,
        "started": 2.0,
        "saved": 3.0,
        "completed": 4.0,
    }

    def __init__(self):
        self.student_ids = []       # index → student pk
        self.item_ids = []          # index → item pk
        self.student_index = {}     # student pk → index
        self.item_index = {}        # item pk → index
        self.matrix = None          # np.ndarray (students × items)

    def build(self, interactions):
        """
        Build matrix from a QuerySet/list of StudentInteraction objects.
        """
        student_set = set()
        item_set = set()
        for interaction in interactions:
            student_set.add(str(interaction.student_id))
            item_set.add(str(interaction.learning_item_id))

        self.student_ids = sorted(student_set)
        self.item_ids = sorted(item_set)
        self.student_index = {sid: i for i, sid in enumerate(self.student_ids)}
        self.item_index = {iid: i for i, iid in enumerate(self.item_ids)}

        self.matrix = np.zeros((len(self.student_ids), len(self.item_ids)))

        for interaction in interactions:
            sid = str(interaction.student_id)
            iid = str(interaction.learning_item_id)
            weight = self.INTERACTION_WEIGHTS.get(interaction.interaction_type, 1.0)
            self.matrix[self.student_index[sid]][self.item_index[iid]] += weight

    @property
    def density(self):
        """Fraction of non-zero cells."""
        if self.matrix.size == 0:
            return 0.0
        return float(np.count_nonzero(self.matrix)) / self.matrix.size

    def item_profile(self, item_pk) -> np.ndarray:
        """Column vector for an item (student-weights)."""
        iid = str(item_pk)
        idx = self.item_index.get(iid)
        if idx is None:
            return None
        return self.matrix[:, idx]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    if a is None or b is None:
        return 0.0
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def build_item_item_similarity(matrix: InteractionMatrix):
    """
    Compute item-item cosine similarity matrix.

    Returns np.ndarray (n_items × n_items) where [i][j] = similarity
    between item i and item j.
    """
    if matrix.matrix is None or matrix.matrix.shape[1] == 0:
        return np.array([])
    n_items = matrix.matrix.shape[1]
    sim = np.zeros((n_items, n_items))
    columns = [matrix.matrix[:, j] for j in range(n_items)]
    for i in range(n_items):
        for j in range(i + 1, n_items):
            s = cosine_similarity(columns[i], columns[j])
            sim[i][j] = s
            sim[j][i] = s
    return sim


def check_eligibility(
    student_pk,
    interactions,
    *,
    min_per_student=CF_MIN_INTERACTIONS_PER_STUDENT,
    min_distinct_items=CF_MIN_DISTINCT_ITEMS_PER_STUDENT,
    min_students_per_item=CF_MIN_STUDENTS_PER_ITEM,
) -> tuple[bool, str]:
    """
    Check if a student qualifies for CF (D19 baselines).

    Student-level baseline:
      - at least 5 meaningful interactions
      - across at least 3 distinct learning items

    Global baseline:
      - candidate items have interaction evidence from at least 3 students
      - overall matrix has enough density
    """
    student_interactions = [
        i for i in interactions
        if str(i.student_id) == str(student_pk)
    ]

    distinct_items = set(str(i.learning_item_id) for i in student_interactions)
    if len(student_interactions) < min_per_student:
        return False, "insufficient_student_interactions"
    if len(distinct_items) < min_distinct_items:
        return False, "insufficient_distinct_items"

    # Global baseline: item density
    item_student_counts = {}
    for i in interactions:
        iid = str(i.learning_item_id)
        item_student_counts.setdefault(iid, set()).add(str(i.student_id))

    for iid in distinct_items:
        if len(item_student_counts.get(iid, set())) < min_students_per_item:
            return False, "insufficient_item_coverage"

    return True, "eligible"


def recommend_cf(
    student_pk,
    interactions,
    learning_items,
    *,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    """
    Item-item collaborative filtering recommendation for a student.

    Returns (recommendations, method) where method is "cf" or "fallback".
    """
    # Check D19 eligibility
    eligible, reason = check_eligibility(student_pk, interactions)
    if not eligible:
        return [], "fallback"

    matrix = InteractionMatrix()
    matrix.build(interactions)

    item_sim = build_item_item_similarity(matrix)

    if item_sim.size == 0:
        return [], "fallback"

    student_idx = matrix.student_index.get(str(student_pk))
    if student_idx is None:
        return [], "fallback"

    # Items the student has already interacted with
    student_row = matrix.matrix[student_idx]
    already_seen = set()
    for j, val in enumerate(student_row):
        if val > 0:
            already_seen.add(matrix.item_ids[j])

    # Candidate items: not yet seen
    candidates = []
    for j, iid in enumerate(matrix.item_ids):
        if iid in already_seen:
            continue
        # Score = max similarity to items the student liked (weighted sum)
        score = 0.0
        sim_col = item_sim[:, j]
        for k, seen_iid in enumerate(matrix.item_ids):
            if seen_iid in already_seen and student_row[k] > 0:
                score += sim_col[k] * student_row[k]
        candidates.append((iid, score))

    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Map item ids to LearningItem objects
    item_id_to_obj = {str(li.id): li for li in learning_items}

    results = []
    for iid, score in candidates[:limit]:
        item_obj = item_id_to_obj.get(iid)
        if item_obj is None:
            continue
        results.append({
            "learning_item_id": iid,
            "title": item_obj.title,
            "item_type": item_obj.item_type,
            "subject_id": str(item_obj.subject_id) if item_obj.subject_id else None,
            "topic": item_obj.topic,
            "relevance_score": round(score, 4),
            "method": "cf_cosine",
            "reason": "Similar to items this student interacted with",
        })

    if not results:
        return [], "fallback"

    return results, "cf"


def recommend_content_based(
    student_pk,
    feature_dict,
    prediction,
    learning_items,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Content-based recommendation fallback using academic relevance.

    Uses the resolver to match academic needs to learning items.
    """
    from ai_engine.resolver import resolve_recommendations

    return resolve_recommendations(
        student_pk,
        feature_dict,
        prediction,
        limit=limit,
    )


def recommend(
    student_profile,
    interactions,
    learning_items,
    feature_dict=None,
    prediction=None,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Top-level recommendation entry point.

    Tries CF first; falls back to content-based.
    """
    cf_results, method = recommend_cf(
        student_profile.id, interactions, learning_items, limit=limit
    )

    if method == "cf":
        return {
            "student_id": str(student_profile.id),
            "method": "cf",
            "recommendations": cf_results,
            "fallback_used": False,
        }

    # Content-based fallback
    cb_results = recommend_content_based(
        student_profile,
        feature_dict or {},
        prediction or {},
        learning_items,
        limit=limit,
    )

    return {
        "student_id": str(student_profile.id),
        "method": "content_based",
        "recommendations": cb_results,
        "fallback_used": True,
        "fallback_reason": "cf not eligible",
    }
