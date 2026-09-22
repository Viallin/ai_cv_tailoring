# 1. Architecture
The architecture is designed to achieve the following goals:
- Ensuring independence of business logic from any LLM provider.
- Separation of user interface and application logic.
- Storing structured data instead of arbitrary text whenever possible.
- Ensuring query reuse and versioning.
- Ensuring validation of every interaction with LLM using typed contracts.
- Ability to replace the AI ​​provider without changing the application layer.
- Persistence of local user data by default.
- Master Resume as the Single Source of Truth
- Structured Data First
   
## 2 High-Level Architecture

> **Status:** the diagram below still describes the target architecture
> (Claims/Competencies/Variants, a real Organization/Role/Project graph)
> — see `docs/domain-model.md`'s "Prototype scope note" callouts for what
> actually exists today. Structurally, current code matches this shape
> with one addition: since Version 2 (`docs/development_plan.md` Phases
> 13-23, done), there's an HTTP boundary between UI and Application — the
> UI Layer is a browser-based React app (`frontend/`), and an API Layer
> (FastAPI, `api/`) wraps the Application Layer services
> (`app/services.py`, `app/pipeline.py`). The Application/Domain/
> Contracts/AI Engine/Provider layers below are unchanged in shape from
> that addition, only in how the UI reaches them. Storage is SQLite via
> SQLModel/Alembic (see `docs/technology_stack.md`), not flat JSON. The
> legacy PySide6 UI (`ui/main_window.py`) called the Application Layer
> in-process, no HTTP boundary — it's frozen and no longer the
> maintained UI (see `README.md`'s Status section).

The UI never interacts directly with the LLM. All interactions with the AI ​​go through the application layer, which coordinates request creation, request execution by the provider, response validation, and mapping to domain models.
``` text
┌─────────────────────────────────────────────────────────────┐
│                          UI Layer                           │
│                                                             │
│  • Resume Upload (PDF / DOCX / TXT)                         │
│  • Resume Graph Explorer                                    │
│  • Vacancy Input                                            │
│  • AI Suggestions  (Claims / Variants / Gaps)               │
│  • CV Builder Preview                                       │
│  • Export Dialog                                            │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│                                                             │
│  Use Cases / Orchestration Services                         │
│  • Ingest Resume                                            │
│  • Build Semantic Resume Graph                              │
│  • Analyze Vacancy                                          │
│  • Map Vacancy To Claims                                    │
│  • Generate Variants For Claims                             │
│  • Build Targeted CV                                        │
│  • Export Resume                                            │
│  Coordinates LLM calls but never directly exposes models    │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                       Domain Layer                          │
│  Core Concept: Semantic Career Graph                        │
│                                                             │
│  Business Models                                            │
│  • Candidate                                                │
│  • Resume (raw + structured)                                │
│  • Vacancy                                                  │
│  • CareerGraph                                              │
│  • Evidence (atomic career fact)                            │
│  • Claim (semantic conclusion of atomic evidences)          │
│  • Competency (semantic conclusion of several claims)       │
│  • Variant (expression of a Claim)                          │
│  • SkillNode                                                │
│  • ExperienceNode                                           │
│                                                             │
│  Business Rules                                             │
│                                                             │
│  • Claims must be atomic and reusable                       │
│  • Variants must not change semantics                       │
│  • Claims are deduplicated across projects                  │
│  • Graph is a source of truth                               │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Contracts Layer                         │
│                                                             │
│  Graph operations                                           │
│  Requests / Responses                                       │
│                                                             │
│  • IngestResumeRequest                                      │
│  • IngestResumeResponse (RawDocument → ParsedResume)        │
│                                                             │
│  • BuildGraphRequest                                        │
│  • BuildGraphResponse (CareerGraph)                         │
│                                                             │
│  • AnalyzeVacancyRequest                                    │
│  • AnalyzeVacancyResponse (RequiredSkills + Signals)        │
│                                                             │
│  • GenerateClaimsRequest                                    │
│  • GenerateClaimsResponse (Claim[] from Resume nodes)       │
│                                                             │
│  • GenerateVariantsRequest                                  │
│  • GenerateVariantsResponse (Claim → Variants mapping)      │
│                                                             │
│  • BuildCVRequest                                           │
│  • BuildCVResponse (Final CV Projection)                    │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                         AI Engine                           │
│  Core Principle: LLM as Semantic Transformer                │
│                                                             │
│  Pipeline Stages:                                           │
│                                                             │
│  • Prompt Builder                                           │
│      - Resume → Evidence extraction prompts                 │
│      - Resume → Evidence normalization prompts              │
│      - Resume → Evidence variants prompts                   │
│      - Resume → Claim inference   prompts                   │
│      - Resume → Competency mapping prompts                  │
│      - Vacancy → skill signal extraction                    │
│      - Vacancy → skills and competency matching prompts     │
│      - Vacancy → new resume projections prompts             │
│                                                             │
│  • LLM Gateway                                              │
│      - provider abstraction layer                           │
│                                                             │
│  • Structured Output Validator                              │
│      - ensures Claims / Graph consistency                   │
│                                                             │
│  • Semantic Mapper                                          │
│      - maps LLM output → Domain models                      │
│                                                             │
│  LLM never returns “final CV text”                          │
│  It only produces structured transformations                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Provider Layer                          │
│                                                             │
│  Gemini Provider                                            │
│  OpenAI Provider                                            │
│  Ollama Provider                                            │
│  Claude Provider                                            │
│  All providers are interchangeable execution backends       │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  External AI Services                       │
│                                                             │
│        Gemini API    OpenAI API    Ollama    Claude API     │
└─────────────────────────────────────────────────────────────┘
``` 
## 3 Core components
### 3.1 UI
Responsible for:
* uploading resumes (PDF / DOCX / TXT)
* exploring semantic Career Graph
* viewing extracted Claims and Variants
* reviewing AI-generated suggestions
* defining target vacancy / role context
* previewing CV projections
* exporting final resume

Never responsible for:
* prompt generation
* LLM API calls
* parsing or validating LLM outputs
* building or modifying domain models directly

### 3.2 Application Services
Coordinates end-to-end semantic transformation workflows.

Examples:
* Ingest Resume
* Build Career Graph
* Analyze Vacancy
* Extract Evidences from Resume Graph
* Generate Variants for Evidences
* Generate Claims and Map competencies based on provided Evidences
* Build Target CV Projection
* Assemble Final CV (Candidate facts + CVProjection, no LLM — app/cv_assembler.py)
* Export Resume

Responsibilities:
* orchestrates pipeline steps
* calls AI Engine when needed
* transforms domain objects through stages
* ensures correct sequencing of graph evolution

Does not contain:
* UI logic
* raw LLM integration details
* business rules of Claim/Graph validity

### 3.3 Domain Models
Contains the core semantic career representation system.

Core entities:
- Candidate
- Vacancy
- Resume (raw + structured)
- CareerGraph (central system object)
- ExperienceNode
- SkillNode
- Evidence (atomic career fact)
  - Example: "Led 2 engineers" in Project A, "led 4 designers" in Project B, "led cross-functional team" in Project C
- Claim (semantic conclusion of evidences)
  - Example: "Experienced people manager" based on evidences A, B, C
- Competency (semantic conclusion of claims)
  - Example: Leadership (supported by claims A, B, C)
- Variant (expression of a Claim)
- CVProjection (output representation of graph for a specific context)

Business rules:
- Claims must be atomic and reusable across contexts
- Variants must preserve semantic meaning of Claims
- CareerGraph is the single source of truth
- CV is a projection, not a stored document
- Domain must be independent of AI providers and prompts

Should NOT depend on:
- AI providers
- prompt structure
- external APIs
- UI layer
### 3.4 AI Engine
Responsible for semantic transformation of career data using LLMs.

It does NOT generate final resumes directly.
#### 3.4.1 Prompt Builder
Responsible for constructing structured transformation prompts.

Includes:
- extracting structured input from Domain Models (Graph / Vacancy / Claims)
- building prompts for:
- Resume → Evidence extraction
- Resume → Evidence normalization
- Resume → Claims and Competence mapping based on evidences
- Vacancy → requirement analysis
- Claim → Variant generation
- injecting context safely
- enforcing output schema requirements

Does NOT:
- interpret LLM output
- decide business logic
- choose final CV structure
#### 3.4.2 LLM Gateway
Responsible for:

- selecting appropriate LLM provider
- selecting model (Gemini / GPT / Claude / local)
- managing generation parameters
- routing requests to provider layer

Does NOT:
- know domain logic
- interpret response structure
- validate semantic correctness
#### 3.4.3 Provider Registry
Responsible for:
- maintaining available LLM providers
- abstracting provider capabilities
- forwarding requests to Provider Layer
- handling fallback strategies (optional)

Providers are interchangeable execution backends.
#### 3.4.4 Response Validator
Responsible for:

- validating structured LLM output against expected schemas (Claims, Variants, Graph updates)
- detecting malformed or incomplete outputs
- rejecting or triggering regeneration
- ensuring semantic consistency at schema level (not business-level correctness)

Does NOT:
- modify business logic
- decide ranking or selection
- interpret meaning beyond schema compliance
### 3.4.5 Provider Layer
Responsible for:
- executing prompts against external LLM APIs
- returning raw model responses
- handling API-level errors and retries

Each provider:
- Gemini Provider
- OpenAI Provider
- Claude Provider
- Local/Ollama Provider

All providers are interchangeable execution adapters and contain no domain knowledge. 

## 4 Project Structure
Предполагаемая структура проекта

Current (as of Version 3 / Phase 24+ — see `README.md`'s Layout table for
the authoritative, most-current version of this list):

| Folder         | Purpose                              |
| -------------- | ------------------------------------ |
| `api/`         | FastAPI HTTP layer (Version 2, Phase 13) — routes only, no business logic |
| `app/`         | Business workflows and orchestration |
| `contracts/`   | Request and response schemas         |
| `db/`          | SQLModel table definitions + engine/session helpers (Phase 13) |
| `domain/`      | Core business entities               |
| `frontend/`    | React/TS/Vite web UI (Version 2, Phase 14+) — the actively developed UI |
| `prompts/`     | Version-controlled prompt templates  |
| `providers/`   | AI provider implementations          |
| `scripts/`     | One-time ops scripts (e.g. the JSON->SQLite migration) |
| `ui/`          | Legacy desktop interface (PySide6, Phase 6) — frozen since before Phase 13, kept for reference only, not the maintained UI |
| `tests/`       | Automated tests (Python); `frontend/src/**/*.test.tsx` for the web UI |
| `docs/`        | Project documentation                |
| `sample data/` | Examples of JD and CVs to test       |

`app/`, `contracts/`, `domain/`, `prompts/`, `providers/` were reused
as-is across the `ui/` → `api/`+`frontend/` transition — the UI change is
purely an additional HTTP boundary in front of the same Application/
Domain/Contracts/AI Engine/Provider layers (see the Version 2 status note
in section 2 above).


## 5 Data Flow
The application contains two primary workflows:

1. Building the semantic Career Graph from the user's source resume(s).
2. Building a tailored CV for a specific job description using the Career Graph.
```text
                 Import Phase
────────────────────────────────────────────────────────
Source Resume
        ↓
Career Graph
        ↓
Local Knowledge Base

                 Generation Phase
────────────────────────────────────────────────────────
Career Graph + Vacancy
        ↓
Resume Projection
        ↓
Export
```

### 5.1 Source CV injection
The goal of this workflow is to transform an uploaded resume into structured, reusable career knowledge.

### Steps

1. User uploads a source resume (PDF / DOCX / TXT).
2. The document is parsed into structured resume data.
3. AI extracts atomic Evidence objects from the parsed resume.
4. Evidence is normalized and linked to Candidate, Organizations, Roles, Projects, Skills, and Technologies.
5. AI generates alternative wording (Variants) for each Evidence item.
6. The validated objects are merged into the Career Graph.
7. The updated Career Graph is stored as the single source of truth.

```text
User
↓
Upload Resume
↓
Resume Parser
↓
Structured Resume
↓
Evidence Extraction
↓
Evidence Validation
↓
Variant Generation
↓
Career Graph Builder
↓
Career Graph
↓
Local Storage
```

---

### 5.2 Tailored CV Generation
The goal of this workflow is to generate a resume projection optimized for a specific vacancy.
### Steps

1. User pastes a job description.
2. AI analyzes the vacancy and extracts structured requirements.
3. The application matches vacancy requirements against the Career Graph.
4. AI identifies missing evidence and proposes rewrite opportunities.
5. The best Evidence variants are selected (or new variants generated when needed).
6. A Resume Projection is assembled.
7. The user reviews and edits the generated resume.
8. The resume is exported to PDF.

```text
User
↓
Paste Vacancy
↓
Analyze Vacancy
↓
Structured Requirements
↓
Career Graph Matching
↓
Gap Analysis
↓
Variant Selection / Generation
↓
Resume Projection
↓
User Review
↓
Export PDF
```

## 6 Prompt System
* Prompts are stored in separate .md files, so changing prompts does not affect the code, allowing you to test different versions of prompts without changing the logic;
* All prompt files contain:
  * Agent role
  * Task description
  * Rules for the model to follow
  * Input data structure
  * Output data structure
* **File names**. The naming convention is "NN_prompt_name_XXX.md", where
  * NN is the step number (currently from 1 to 5),
  * **prompt_name** is the step description
  * XXX is the specific stage of the step. 
  * Current example files:
    * 01_cv_parser_XXX.md - prompts responsible for parsing the resume master
    * 02_jd_parser_XXX.md - prompts responsible for parsing the job description
    * 03_cv_jd_matcher_XXX.md - prompts responsible for matching skills from the resume and the job description, determining the gap between experience and the job description, and assessing criticality
   * 04_rewrite_planner_XXX.md - prompts responsible for creating an editing plan
   * 05_rewrite_bullets_XXX.md - prompts responsible for suggesting specific edits to the text
  * As of Phase 8, all five are real, wired-up files:
    `01_cv_parser_v1.md`, `02_jd_parser_v1.md`, `03_cv_jd_matcher_v1.md`,
    `04_rewrite_planner_v1.md`, `05_rewrite_bullets_v1.md`. 03/04/05 replace
    Phase 5-7's single collapsed `03_cv_builder_v1.md` call (now archived)
    with the three real stages this section originally described.
* **prompts/archive/** holds superseded drafts that no longer match their
  contract (kept for history only). Never two same-numbered files both
  live in `prompts/` itself with different schemas — if a prompt is
  replaced, move the old one to `archive/` in the same change.
* **Prompt Builder** is responsible for loading and substituting data 
* Prompts do not contain business logic.



## 7 LLM Providers
The application depends only on the ILLMProvider interface. Specific providers implement the same contract, allowing you to switch between providers without changing the business logic.
``` text
Application
↓
ILLMProvider
↓
GeminiProvider
OpenAIProvider
OllamaProvider
```
## 8 Configuration
The application configures:
* LLM provider
* model
* API keys
* folder with a list of prompts
* logging level
* export folder

## Error Handling
## Error Handling

The application should handle errors predictably and consistently across all layers. Errors are treated as expected outcomes that must be surfaced to the user or calling component in a structured way.

### General Principles

- Never expose raw exceptions or LLM responses directly to the UI.
- Every layer is responsible for handling only the errors it can reasonably recover from.
- Unexpected errors should be logged with sufficient context for debugging.
- User-facing error messages should be clear, actionable, and independent of provider-specific terminology.
- Business logic should not depend on exception messages returned by external services.

### Error Categories

Errors should be classified into well-defined categories.

| Category | Description |
|----------|-------------|
| ConfigurationError | Missing or invalid application configuration. |
| PromptError | Missing prompt template, invalid placeholders, or prompt rendering failure. |
| ProviderError | Failure while communicating with an LLM provider. |
| ValidationError | AI response does not match the expected contract. |
| ParsingError | Unable to deserialize or interpret the provider response. |
| StorageError | Failure while reading or writing local data. |
| ExportError | Failure during document export. |
| UnexpectedError | Any unhandled internal application error. |

### Error Propagation

Errors should be translated when crossing architectural boundaries.

For example:

```text
Gemini SDK Exception
        ↓
ProviderError
        ↓
Application Error
        ↓
User-friendly message
```

Each layer should expose domain-specific errors rather than implementation-specific exceptions.

### Logging

All unexpected errors should be logged.

Logs should include:

- timestamp
- operation name
- provider (if applicable)
- model name (if applicable)
- error category
- stack trace (debug mode only)

Sensitive information such as API keys, personal data, prompts, or generated resume content must never be written to logs.

### Recovery Strategy

Whenever possible, the application should allow the user to recover without losing work.

Examples:

- Retry transient provider failures.
- Preserve user edits after AI failures.
- Allow regeneration after validation failures.
- Continue working offline with existing local data when external AI services are unavailable.

## Testing Strategy
The project should be designed to be easily testable at every architectural layer. Business logic must be verifiable independently from the UI, AI providers, and external services.

### Testing Principles
- Business logic should be testable without an LLM.
- Every architectural layer should be testable in isolation.
- External dependencies should be mocked whenever possible.
- Tests should validate behavior rather than implementation details.
- AI providers should never be required for unit tests.
- Every bug should result in a regression test whenever practical.

### Test Pyramid
The project follows a layered testing strategy.

| Test Type | Purpose |
|-----------|---------|
| Unit Tests | Verify domain models, business rules, and application services in isolation. |
| Contract Tests | Validate request and response contracts, serialization, and schema validation. |
| Prompt Tests | Verify prompt rendering, placeholder substitution, and required variables. |
| Provider Tests | Verify communication with individual LLM providers. External API calls should be mocked whenever possible. |
| Integration Tests | Verify complete application workflows across multiple layers. |
| UI Tests | Verify critical user interactions and end-to-end workflows. |

### Unit Testing
Unit tests should focus on deterministic business logic.

Examples:
- Resume scoring
- Vacancy analysis workflow
- Resume generation orchestration
- Export formatting
- Domain model validation

Unit tests must not depend on:
- network access
- filesystem (unless explicitly testing storage)
- LLM providers
- UI components

### Contract Testing
Every request and response contract should be validated.
Tests should verify:
- required fields
- optional fields
- invalid input
- serialization
- deserialization

### Prompt Testing

Prompt templates are considered part of the application's source code.

Tests should verify:
- all required placeholders exist
- no unresolved variables remain
- prompt rendering succeeds
- expected prompt structure is preserved
### AI Testing Philosophy

LLM-generated content should not be tested by comparing exact text outputs.

Instead, tests should verify:

- response structure;
- contract validation;
- business workflow;
- error handling;
- deterministic transformations.

The quality of generated text should be evaluated separately through manual review or dedicated evaluation datasets, not traditional unit tests.

### Provider Testing

Each provider implementation should be tested independently.

Tests should verify:
- request formatting
- provider configuration
- error handling
- response mapping

Network communication should be mocked for automated testing whenever possible.

### Integration Testing

Integration tests verify complete business workflows.

Typical scenarios include:

- Analyze vacancy
- Generate resume
- Rewrite experience
- Export resume

Integration tests should exercise multiple architectural layers together while minimizing reliance on external services.

### UI Testing

UI tests should focus on user workflows rather than individual widgets.

Critical scenarios include:

- Creating a resume
- Editing generated content
- Applying AI suggestions
- Exporting documents

### Test Data

Test data should be:

- deterministic
- reusable
- representative of real-world resumes and job descriptions
- stored separately from production data

Sensitive or personally identifiable information must never be included in test fixtures.

### Continuous Quality

Every new feature should include appropriate automated tests.
Whenever possible:

- bug fixes should include regression tests;
- new contracts should include validation tests;
- new prompts should include rendering tests;
- new providers should include provider-specific tests.
## Future Extensibility
* Auth service
  * Authorization
  * Service subscription
  * server storage
  * Version history
* AI
   * additional LLM-providers;
   * Agent workflows
   * RAG
   * Local models
* CV
  * New export formats;
  * Cover letters generation;
  * Guides for writing a better CV
* Job hunting board: 
  * Kanban
  * Interview preparation
  * Interview notes
  * Reminders