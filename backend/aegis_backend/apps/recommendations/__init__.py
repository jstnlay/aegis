"""
Recommendations app.

The HTTP surface `ai_engine/recommender.py` never had: one read endpoint for a
student's recommendations and one write endpoint for the interaction signal that
makes collaborative filtering possible.

Separate from `apps.analytics` because analytics is the read-only aggregation
layer with no models, and this app has a write path.
"""

default_app_config = "apps.recommendations.apps.RecommendationsConfig"