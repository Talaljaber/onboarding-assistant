"""Document import for the knowledge editor (P12.1): extract -> (optional) model titles (P13.4) -> chunk -> (optional) organize -> drafts.

Uploaded text never becomes answerable on its own: the admin approves each passage, which is then added
as a normal K-row through `KnowledgeBase.add_many` (same history and reindex as `POST /api/kb`).
"""
