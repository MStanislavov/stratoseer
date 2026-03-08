# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI Executive Assistant Network** — a multi-agent career intelligence system with a web GUI. It acts as a "digital board of advisors" running scouts, planners, a verifier, and an auditor, all governed by explicit policy-as-code.

This project is at specification stage. The `README-setup.md` is the authoritative spec.

## Tech Stack

- **Orchestration**: LangGraph (StateGraph) for agent pipelines, LangChain for LLM abstractions
- **Backend**: FastAPI (Python) + Pydantic v2 (API schemas, DB models, validation)
- **Inter-agent DTOs**: `TypedDict` for LangGraph state (idiomatic); Pydantic for API boundaries and persistence
- **Frontend**: HTMX + HTML/CSS (single-service, served by FastAPI)
- **Storage**: PostgreSQL (entities) + append-only JSONL (audit logs)
- **Real-time**: SSE (Server-Sent Events) for run progress streaming
- **Policies**: YAML files under `/policy/`, read-only in GUI, versioned via git
- **Phase 1 agents**: Mock/stub implementations (no real LLM calls), swappable for real LLMs later
- **Testing**: pytest

## Commands (once implemented)

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the FastAPI dev server
uvicorn app.main:app --reload

# Run tests
pytest

# Run a specific test file
pytest tests/test_policy_engine.py

# Lint
ruff check .
```

## Architecture

### Multi-Profile Workspaces

Each profile (e.g., "Architect", "Developer") is an independent workspace. All runs, opportunities, and cover letters are scoped to a profile. The GUI provides a profile switcher on the dashboard.

### LangGraph Agent Pipelines

Three `StateGraph` definitions: **daily**, **weekly**, **cover_letter**. Each graph's nodes are agents; edges are conditional routing governed by the policy engine.

```
StateGraph (per pipeline mode)
  Nodes = agents (retriever, extractor, coordinator, ceo, cfo, cover_letter, verifier, audit_writer)
  Edges = conditional routing based on policy engine
  State = TypedDict shared across nodes in a single graph execution
  Callbacks = feed SSE stream for real-time GUI updates
```

### Key Design Rules

**Tooling boundaries** (enforced by policy engine, not convention):
- Retriever agents: network tools allowed
- Planner agents (CEO/CFO/Coordinator): no retrieval; structured inputs only
- Cover letter agent: reads CV + selected JD + extracted requirements only

**Evidence-first contract**: Every claim referencing external info must have `EvidenceItem` (URL + SHA-256 hash + snippet). Missing evidence -> verifier fails the run or forces "Unknown" section.

**Verifier is deterministic** (not an LLM): validates JSON schema, evidence coverage, confidence thresholds, policy compliance, dedup, and output bounds. Fails hard or marks "partial" (safe degradation).

**Audit bundle** stored under `artifacts/runs/<run_id>/`: input profile hash, policy version hash, prompt template IDs + param hashes, tool call hashes, intermediate outputs, verifier report, final artifacts.

### Core Data Entities

- `UserProfile` — targets, constraints, skills, CV; one per workspace
- `SourceConfig` — allowlisted sources + query templates per scout
- `Run` — immutable execution record
- `Artifact` — briefs, opportunities, cover letters
- `EvidenceItem` — id, type, url, retrieved_at, content_hash (sha256), snippet, metadata
- `Claim` — text, requires_evidence bool, evidence_ids[], confidence
- `VerifierReport` — per-claim and overall pass/fail/partial status
- `PolicyVersion` — versioned, testable policy snapshots

### Policy Files

All policies live in `/policy/*.yaml`. The policy engine loads and enforces:
- Tool/source allowlists and denylists per agent
- Step budgets and token limits (`policy/budgets.yaml`)
- Data boundary rules (which fields cross which agent boundaries)
- Redaction rules for PII in logs

Policy unit tests must verify that forbidden behavior is actually blocked.

### API Endpoints

All endpoints use `/api` prefix. Profile-scoped resources nest under `/api/profiles/{profile_id}`.

```
# Profile management
POST   /api/profiles
GET    /api/profiles
GET    /api/profiles/{profile_id}
PUT    /api/profiles/{profile_id}
DELETE /api/profiles/{profile_id}
POST   /api/profiles/{profile_id}/cv

# Run lifecycle
POST /api/profiles/{profile_id}/runs                          # Start run (mode: daily|weekly|cover_letter)
GET  /api/profiles/{profile_id}/runs                          # List runs
GET  /api/profiles/{profile_id}/runs/{run_id}                 # Run details
GET  /api/profiles/{profile_id}/runs/{run_id}/stream          # SSE progress stream
POST /api/profiles/{profile_id}/runs/{run_id}/cancel          # Cancel run

# Audit & replay
GET  /api/profiles/{profile_id}/runs/{run_id}/audit           # Audit trail
GET  /api/profiles/{profile_id}/runs/{run_id}/verifier-report # Verifier report
POST /api/profiles/{profile_id}/runs/{run_id}/replay          # Replay (strict|refresh)
GET  /api/profiles/{profile_id}/runs/{run_id}/diff/{other_run_id}

# Opportunities & cover letters
GET  /api/profiles/{profile_id}/opportunities
GET  /api/profiles/{profile_id}/opportunities/{opportunity_id}
POST /api/profiles/{profile_id}/cover-letters
GET  /api/profiles/{profile_id}/cover-letters
GET  /api/profiles/{profile_id}/cover-letters/{letter_id}

# Policies (read-only)
GET /api/policies
GET /api/policies/{policy_name}
```

### Replay Modes

- **Strict**: use stored tool responses (no network calls)
- **Refresh**: re-fetch URLs, compare content hashes, flag drift
- Both produce a **diff report** (opportunity changes, trend evidence changes, priority shifts)

## Implementation Phases

1. **Phase 1**: Policy engine + LangGraph daily pipeline (job scout, mock agents) + verifier + audit writer + PostgreSQL + minimal GUI + SSE streaming
2. **Phase 2**: Add certs + trends scouts; add CEO/CFO/coordinator; opportunities browser; full multi-profile workspace switching
3. **Phase 3**: Cover letter pipeline + strict replay + diff UI

## Quality Bars (from spec)

- Tests for policy engine, verifier, and replay are required
- All agent outputs must be typed (Pydantic for API, TypedDict for LangGraph state)
- Clear retrieval/extraction vs. planning separation
- No silent failures; safe degradation must be explicit and declared

---

## Project Memory (Claude Code — update this as work progresses)

### Status
- **Current stage**: Steps 0-8 complete, testing/hardening/packaging remaining
- **Last updated**: 2026-03-08

### Key Decisions
- Orchestration: LangGraph (StateGraph) + LangChain
- Inter-agent DTOs: TypedDict (LangGraph state), Pydantic v2 (API/persistence)
- Storage: PostgreSQL + append-only JSONL
- Real-time: SSE for run progress
- Phase 1 agents: mock/stub only, swappable for real LLMs later
- Profiles = independent workspaces, all endpoints scoped under profile_id

### Execution Plan
Full 12-step plan lives in: `.claude/plans/rosy-zooming-fog.md`
- Step 0: Scaffolding (dirs, pyproject.toml, empty modules)
- Steps 1-4: Phase 1 (policy engine, DB+schemas, daily pipeline, GUI)
- Steps 5-6: Phase 2 (all scouts, weekly pipeline, multi-profile)
- Steps 7-8: Phase 3 (cover letters, replay+diff)
- Step 9: Testing pass
- Step 10: Evaluation & hardening
- Step 11: Docker packaging
- Parallelizable: 1+2 together; 4+5+8 after 3

### Implementation Progress
<!-- Update this section as steps are completed -->
- [x] Step 0: Scaffolding
- [x] Step 1: Policy engine + verifier + audit writer
- [x] Step 2: DB + schemas + profile CRUD API
- [x] Step 3: LangGraph daily pipeline + run API + SSE
- [x] Step 4: HTMX GUI (minimal)
- [x] Step 5: Additional scouts + weekly pipeline
- [x] Step 6: Multi-profile workspace
- [x] Step 7: Cover letter pipeline
- [x] Step 8: Replay + diff
- [ ] Step 9: Testing & quality pass (147 tests pass, but no formal quality sweep yet)
- [ ] Step 10: Evaluation & hardening
- [ ] Step 11: Docker packaging (no Dockerfile/docker-compose.yml yet)

### Patterns & Notes
- 147 tests pass (pytest) as of 2026-03-08
- No alembic migration scripts generated yet (alembic/ scaffolding only)
- No .env.example created yet
- test_api_runs.py uses asyncio.sleep for background task testing — acceptable for Phase 1
