"""
Multi-provider task management integration layer.

Providers: Trello (existing), Jira, Microsoft (Planner / To Do)

Entry points:
  - base.py          — abstract TaskProvider interface + normalized models
  - encryption.py    — Fernet token encryption/decryption
  - registry.py      — provider factory by ProviderType
  - oauth/           — OAuth2 authorization code flows
  - providers/       — concrete TaskProvider implementations
"""
