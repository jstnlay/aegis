"""
Portfolio app.

Student-authored showcase entries (paperwork, term exams, recitations and
other school activities) with an optional link to the work. Text-only by
design: this host has no persistent disk, so uploaded files would vanish on
redeploy — a link to work hosted elsewhere is the honest substitute.
"""

default_app_config = "apps.portfolio.apps.PortfolioConfig"
