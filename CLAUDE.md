# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily Paper 2 is a research paper management and recommendation system with a Python FastAPI backend and React frontend. It fetches papers from arXiv/Hugging Face, processes them with local AI (Ollama), stores them in SQLite with vector embeddings, and provides personalized recommendations.

## Development Commands

### Starting the Full Stack
```bash
./start_server.sh
```
This launches both backend (port 18000) and frontend (port 15173) concurrently with proper environment variables.

### Backend Testing
```bash
# Run all tests
pytest

# Run only unit tests (excludes live network calls)
pytest -m "not e2e"

# Run only end-to-end tests
pytest -m e2e

# Run tests for a specific module
pytest tests/test_paper_parse_unit.py tests/test_paper_parse_e2e.py
```

### Frontend Development
```bash
cd website/frontend
npm run dev          # Development server
npm run build        # Production build
npm run test         # Unit tests
```

### CLI Tools (for debugging/manual operations)
```bash
# Fetch papers
python scripts/paper_fetch_cli.py search --query "machine learning" --limit 10

# Parse papers (OCR)
python scripts/paper_parse_cli.py paper arxiv:2603.05500

# Generate embeddings
python scripts/paper_embedding_cli.py embed

# Get recommendations
python scripts/paper_recommand_cli.py recommend --algorithm fusion --top-k 20

# Manage activities
python scripts/paper_activity_cli.py get arxiv:2603.05500
python scripts/paper_activity_cli.py update arxiv:2603.05500 --user-notes "My notes"

# Generate reports
python scripts/paper_report_cli.py create daily-2026-03-11 --report-date 2026-03-11
```

## Architecture

### Service-Oriented Backend Structure

The backend follows a clean service-oriented architecture with modular, independently testable services:

```
service/
├── fetch/              # Paper fetching from arXiv, Hugging Face
├── parse/              # PDF-to-markdown conversion via Ollama OCR
├── embedding/          # Vector embeddings with sqlite-vec
├── recommand/          # Plugin-based recommendation system
├── activity_management/ # User interaction tracking (likes, notes)
└── report_management/  # Daily report generation
```

**Key principle:** Each service is independently usable with its own CLI, configuration section in `config.yaml`, and test suite. Services share the same SQLite database (`data/papers.db`) but otherwise remain decoupled.

### Plugin-Based Recommendation System

Located in `service/recommand/`, this is the core algorithmic component. Uses a plugin architecture where each recommendation algorithm implements `RecommendationPlugin.recommend()` returning `dict[paper_id, score]`.

Available plugins (configurable via `config.yaml` under `paper_recommand.plugins`):
- **semantic**: Vector similarity search using embeddings
- **interaction**: Collaborative filtering based on user likes/notes, with penalty for disliked papers
- **time**: Freshness decay based on publication date
- **fusion**: Weighted combination of all enabled plugins

To add a new recommendation algorithm:
1. Create a class inheriting from `service/recommand/plugins/base.py:RecommendationPlugin`
2. Implement `name` property and `recommend(request: PaperRecommandRequest) -> dict[str, float]`
3. Register it in `PaperRecommandService.__init__()` with a fusion weight

### Background Task System (Skills)

The backend uses a skill-based task execution system for long-running AI workflows. Skills are defined as markdown files in `skills/` directory that Claude executes as subprocess tasks.

**Key components:**
- `website/backend/tasks.py:TaskManager` - Manages subprocess lifecycle, stdout capture, status tracking
- `website/backend/tasks.py:SkillCommandBuilder` - Builds claude commands from skill files
- `skills/paper-analysis/SKILL.md` - Deep paper interpretation workflow (fetch → parse → question-driven analysis → report generation)
- `skills/paper-recommand/SKILL.md` - Daily report generation workflow

Skills are triggered via API endpoints (`POST /api/tasks/paper-analysis`, `POST /api/tasks/daily-report`) and run asynchronously with real-time log streaming.

### Database Schema

All services share `data/papers.db` (SQLite with sqlite-vec extension):

- `papers` - Paper metadata (id, title, abstract, local_pdf_path, etc.)
- `paper_parses` - OCR status and parsed markdown paths
- `paper_embeddings` - Vector embeddings for semantic search
- `activity` - User interactions (likes, notes, AI reports, recommendation records)
- `report` - Daily generated reports with related paper IDs

### Frontend Architecture

React 19 with TypeScript, using:
- **UI**: Ant Design 5.24
- **State**: Zustand stores in `website/frontend/src/stores/`
- **Routing**: React Router DOM 7 with routes `/daily-report`, `/paper-explore`, `/settings`
- **API**: TanStack React Query for data fetching
- **Markdown**: react-markdown with rehype-katex for math rendering

Key design patterns from `frontend_design.md`:
- Left sidebar navigation (collapsible on mobile)
- Three main views: Daily Report, Paper Explore, Settings
- Tables with inline action buttons (view details, read paper, AI analysis, add notes)
- Async task monitoring with live log streaming in Settings page

## Configuration

All configuration centralized in `config.yaml` at project root. Environment variables can override config values (e.g., `DB_PATH`, `TASK_LOG_DIR`, `SKILLS_DIR`).

**Critical Ollama settings:**
- OCR model: `paper_parse.ollama.model = "glm-ocr"`
- Embedding model: `paper_embedding.ollama.model = "qwen3-embedding:0.6b"`
- Endpoint: `http://localhost:11434`

**Recommendation weights** (tunable per algorithm):
- `paper_recommand.plugins.{semantic,interaction,time}.weight`

## Testing Strategy

Tests are categorized by markers:
- Unit tests (`test_*_unit.py`) - No external dependencies, fast
- E2E tests (`test_*_e2e.py`) - Live network/external service calls, marked with `@pytest.mark.e2e`

Each service module has paired unit and e2e tests. Run `pytest -m e2e` to exclude tests requiring network/Ollama.

## Common Patterns

### Adding a New Service Module

1. Create `service/<name>/` with `__init__.py`, config loader, repository class, service class
2. Add models to `models/<name>.py` if needed
3. Create `scripts/<name>_cli.py` for manual testing
4. Write unit and e2e tests in `tests/`
5. Add configuration section to `config.yaml`
6. Integrate with backend API if needed (`website/backend/api.py`)

### Working with Skills

Skills are Claude Code workflows defined as markdown. To modify a workflow:
1. Edit the `SKILL.md` file in `skills/<skill-name>/`
2. The skill should be a standalone workflow with clear steps
3. Use bash scripts embedded in the skill for CLI operations
4. Return structured output that can be parsed by the backend

### Database Migrations

The codebase uses direct SQL schema creation in repository classes. When modifying schema:
1. Update the `CREATE TABLE` statement in the relevant repository
2. No need for consider backward compatibility.
3. Migrate current database.

## Important Constraints

- **Ollama must be running** locally for OCR and embedding operations
- **sqlite-vec extension** must be available for vector similarity search
- **Python 3.11+** required for modern type syntax
- Frontend build requires **Node.js** and npm
- Background tasks (skills) require **Claude Code CLI** to be installed and available in PATH
