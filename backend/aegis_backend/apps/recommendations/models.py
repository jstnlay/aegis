"""
No models.

`StudentInteraction` and `LearningItem` live in `apps.cms` because the CMS owns
the content lifecycle; this app only reads them and writes interactions through
that model. Defining a second interaction model here would split the CF signal
across two tables.
"""