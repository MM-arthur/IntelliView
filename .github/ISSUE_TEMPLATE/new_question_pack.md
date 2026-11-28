---
name: New question pack proposal
about: Propose a role pack for the open question bank (good first issue!)
labels: enhancement, good first issue
---

**Target role / pack id** (required)
e.g. `data-analyst`, `devops-sre`, `frontend-vue`.

**Scope** (required)
Which 4-8 key points should this pack cover?

**3 sample questions**
Include at least one `follow_up` that has real discrimination — the goal is to expose the edge of someone's knowledge, not to check memorization.

---
Proposer checklist:
- [ ] Questions are not LeetCode originals or leaked interview questions from a specific company.
- [ ] `id` is lowercase letters/digits/hyphens and globally unique (see existing packs in `questions/`).
- [ ] At least 8 questions planned, with easy / medium / hard all represented.

Maintainer note: a full pack (12 questions, validated via `python cli.py bank validate questions/<id>.json`) can be submitted directly as a PR instead.
