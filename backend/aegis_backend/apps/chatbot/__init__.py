"""
Phase 9 chatbot app.

Local-first, least-privilege, role-aware chatbot with deterministic
intent/rule layer. Physics: the application remains authoritative —
the LLM never gets direct DB access.
"""
default_app_config = "apps.chatbot.apps.ChatbotConfig"
