# ADK Technical Architecture Refactor Plan

## 1. Background

The current `adk/` implementation has a clear high-level shape:

- Python preprocesses diff and batches input.
- `planner_agent` decides which review domains are active.
- Multiple reviewer agents run in parallel.
- Python merges findings and posts review comments.

This direction is reasonable and cost-efficient, but the current implementation still depends on several weak text contracts between Python and LLM agents. As a result, the system is easy to run but not yet robust enough to serve as a long-term review platform.

This document focuses on architecture hardening, not prompt tuning.

## 2. Current Architecture Assessment

### 2.1 Strengths

- Clear layering: preprocessing, planning, reviewing, merging, posting.
- Good token strategy: batch split, test-file filtering, inactive-domain skip.
- Reviewer responsibilities are already split by domain, which is a good base for future extensibility.
- Findings merge and verdict generation are deterministic in Python instead of another LLM pass.

### 2.2 Core Problems

#### A. Weak state contracts cause fail-open behavior

Current examples:

- `planner_agent` writes `active_domains` as raw JSON text.
- `gate.py` parses that text dynamically and silently falls back to `[]`.
- If parsing fails, all reviewers may be skipped while the pipeline still appears successful.
- Reviewer outputs are also parsed leniently; invalid JSON is treated as empty findings.

Impact:

- Silent false negatives.
- Operational metrics look healthy even when review quality is degraded.
- Planner and reviewer output instability is converted into "no issue found".

#### B. Diff model is not normalized enough

Current examples:

- `parse_diff()` preserves paths like `a/src/app.py`.
- Tool functions read files using repo-relative real paths.
- Standard unified diff input can therefore break cross-file inspection.

Impact:

- `file_read()` and `grep()` cannot reliably retrieve repository context.
- Signature-change and caller-analysis prompts become less trustworthy.
- The architecture depends on input formatting details instead of a stable internal representation.

#### C. Domain routing is prompt-driven, not contract-driven

Current examples:

- Planner prompt defines domain rules in natural language.
- Reviewer prompt scope and actual injected file filters are not always aligned.
- `backend_reviewer` is expected to reason about some schema-contract issues, but its file filter excludes SQL/migration hunks.

Impact:

- Domain boundaries drift over time.
- Adding a new reviewer requires editing multiple places by hand.
- Architecture correctness relies on humans remembering hidden coupling.

#### D. Orchestration is coupled to deprecated ADK APIs

Current examples:

- `root_agent.py` depends on deprecated `SequentialAgent` and `ParallelAgent`.
- The code already documents this as a temporary compromise.

Impact:

- Migration cost increases over time.
- Core business logic is mixed with framework-specific orchestration decisions.
- Testing architecture independently from ADK is harder.

#### E. Missing platform-level test and observability layer

Current gaps:

- No dedicated tests for planner parsing failures.
- No dedicated tests for diff path normalization.
- No explicit run status model for skipped / invalid / failed reviewer runs.
- No review-quality telemetry per stage.

Impact:

- Regressions are discovered late.
- Production incidents are hard to triage.
- Benchmarking exists, but architecture correctness is not strongly protected.

## 3. Refactor Goals

### 3.1 Goals

- Make the pipeline fail-safe instead of fail-open.
- Replace weak text contracts with validated structured contracts.
- Separate framework-independent review logic from ADK integration.
- Make reviewer registration declarative and scalable.
- Improve testability, observability, and migration readiness.

### 3.2 Non-goals

- Not redesigning all prompts in this phase.
- Not changing the external CLI interface unless needed.
- Not introducing a full distributed task system.
- Not replacing LLM reviewers with static analyzers.

## 4. Target Architecture

### 4.1 Design Principles

- Python owns control flow, validation, and safety decisions.
- LLMs produce judgments, not infrastructure state transitions.
- Every stage returns a typed result with explicit status.
- Planner failure must trigger a conservative fallback, not a silent skip.
- Reviewer registration should be data-driven.
- ADK should become an adapter layer, not the center of the architecture.

### 4.2 Proposed Layering

```text
CLI / Integration Layer
  - adk/run.py
  - PR fetch / comment posting

Pipeline Core
  - batch execution
  - planner fallback policy
  - reviewer dispatch
  - findings merge
  - run status aggregation

Review Contracts
  - DiffSummary
  - ReviewPlan
  - ReviewerResult
  - FindingsEnvelope
  - RunDiagnostics

Domain Registry
  - reviewer specs
  - file filters
  - output keys
  - tool policies

Framework Adapters
  - ADK adapter
  - future Workflow adapter
```

### 4.3 Proposed Data Contracts

Suggested internal models:

- `NormalizedDiffFile`
  - `display_path`
  - `repo_path`
  - `lang`
  - `diff_text`
- `ReviewPlan`
  - `active_domains: list[str]`
  - `planner_status: success | fallback | invalid`
  - `reason: str | None`
- `ReviewerResult`
  - `domain`
  - `status: skipped | success | invalid_output | failed`
  - `findings: list[Finding]`
  - `error: str | None`
- `PipelineBatchResult`
  - `plan`
  - `reviewer_results`
  - `diagnostics`

The important change is that "empty findings" and "invalid output" must no longer be represented the same way.

## 5. Recommended Refactor Roadmap

### Phase 0: Safety Hardening Without Framework Rewrite

Goal: eliminate the most dangerous correctness risks while preserving the current ADK pipeline shape.

Changes:

- Normalize diff file paths in `parse_diff()`.
- Distinguish `display_path` from `repo_path`.
- Add strict parsing helpers for planner output and reviewer output.
- When planner output is invalid, fall back to a conservative domain set instead of `[]`.
- When reviewer output is invalid, mark that reviewer as `invalid_output` and surface diagnostics.
- Align reviewer file filters with prompt expectations.
- Add unit tests for these contracts.

Recommended fallback policy:

- If planner output is invalid: activate all reviewers for that batch.
- If a reviewer output is invalid: keep other reviewers' results, but record the batch as degraded.

Expected value:

- Major reduction in silent false negatives.
- Minimal code churn.
- Good short-term ROI.

### Phase 1: Reviewer Registry and Declarative Assembly

Goal: remove hand-maintained coupling between prompts, filters, output keys, and root assembly.

Changes:

- Introduce a `ReviewerSpec` registry, for example:
  - `domain`
  - `agent_name`
  - `output_key`
  - `file_filters`
  - `instruction`
  - `tools`
- Generate reviewer agents from the registry instead of hand-writing nearly identical modules.
- Generate merge inputs from the same registry.
- Generate planner-visible domain metadata from the same source where possible.

Expected value:

- Easier to add new reviewers.
- Reduced configuration drift.
- Fewer multi-file manual updates.

### Phase 2: Move More Routing Logic Into Python

Goal: use LLMs for judgment, not basic classification that can be deterministic.

Changes:

- Add a Python pre-planner that infers candidate domains from:
  - file paths
  - extensions
  - annotations
  - keyword heuristics
- Pass candidate domains to planner as bounded choices.
- Optionally let planner only prune or confirm candidates, not invent arbitrary domains.
- Move file-level routing and hunk filtering into Python rather than prompt text.

Expected value:

- Smaller prompts.
- Better consistency across runs.
- Less planner drift.

### Phase 3: Introduce a Core Pipeline Abstraction

Goal: decouple business logic from ADK-specific orchestration.

Changes:

- Create framework-agnostic pipeline components:
  - `build_review_plan(...)`
  - `run_reviewer(...)`
  - `merge_findings(...)`
  - `summarize_diagnostics(...)`
- Keep ADK agent definitions inside an adapter module.
- Ensure the same core contracts work with both current ADK and future orchestration options.

Expected value:

- Safer migration to ADK Workflow APIs later.
- Better unit-test coverage without booting full agent runtime.
- Clear separation between product logic and framework glue.

### Phase 4: Migrate Off Deprecated Orchestration APIs

Goal: remove dependence on deprecated `SequentialAgent` / `ParallelAgent`.

Changes:

- Rebuild orchestration using newer ADK workflow primitives only after the core abstraction exists.
- Keep the migration small by swapping the adapter layer, not redesigning the whole pipeline.
- Add compatibility tests comparing old and new orchestration outputs for the same fixture set.

Expected value:

- Lower migration risk.
- Better future maintainability.

## 6. Concrete Module Restructure

Suggested direction:

```text
adk/
  run.py
  prompts.py
  adapters/
    adk_runtime.py
  contracts/
    diff_models.py
    review_plan.py
    reviewer_result.py
  pipeline/
    batch_runner.py
    planner_fallback.py
    merge.py
    diagnostics.py
  registry/
    reviewers.py
  reviewers/
    android.py
    backend.py
    security.py
    concurrency.py
    caching.py
    db_schema.py
    frontend.py
  parsing/
    diff_parser.py
```

Notes:

- Keep `shared/` for repo/tooling integration and common schemas.
- Keep review-domain semantics inside `adk/registry/` and `adk/reviewers/`.
- Avoid spreading output keys and file-filter rules across multiple unrelated modules.

## 7. Key Decisions

### Decision 1: Fail-safe over fail-open

Recommendation:

- Invalid planner output should increase review coverage, not reduce it.
- Invalid reviewer output should degrade the run status, not disappear.

Why:

- In automated code review, false negatives are more dangerous than extra token cost.

### Decision 2: One source of truth for reviewer metadata

Recommendation:

- Domain names, filters, output keys, and reviewer construction should come from one registry.

Why:

- This removes hidden coupling and makes architecture evolution predictable.

### Decision 3: Stable internal diff model

Recommendation:

- Normalize all input diffs into repo-relative paths before any agent sees them.
- Preserve original display text only for UI or comment output.

Why:

- Reviewer tools should depend on internal truth, not raw external formatting.

### Decision 4: Typed diagnostics as first-class output

Recommendation:

- Every batch should produce diagnostics such as:
  - planner invalid
  - reviewer skipped
  - reviewer invalid output
  - reviewer tool failure

Why:

- This enables alerting, QA, and trustworthy benchmark interpretation.

## 8. Testing Strategy

### 8.1 Must-have Unit Tests

- `parse_diff()` normalizes `a/` and `b/` prefixes correctly.
- planner output parser rejects malformed JSON explicitly.
- planner fallback activates conservative domain coverage.
- reviewer output parser distinguishes invalid output from empty findings.
- backend / db_schema routing rules match configured file filters.
- merge logic preserves highest severity for duplicate findings.

### 8.2 Must-have Integration Tests

- Local diff run with standard unified diff format.
- Batch with all test files returns skipped batch safely.
- Invalid planner output still results in active reviewers.
- One reviewer returns malformed JSON while others succeed.
- Signature change triggers successful `grep`/context lookup on normalized paths.

### 8.3 Benchmark / Regression Tests

- Maintain a fixed fixture set with known expected findings.
- Track:
  - finding recall
  - invalid-output rate
  - degraded-run rate
  - token cost per batch

## 9. Observability Recommendations

Add structured logs for:

- batch id
- changed files
- planner status
- active domains
- reviewer status by domain
- invalid-output reasons
- token usage by stage
- final degraded/non-degraded run flag

Recommended success metrics:

- `planner_invalid_rate`
- `reviewer_invalid_rate`
- `degraded_batch_rate`
- `finding_recall_on_fixture_set`
- `average_tokens_per_batch`

## 10. Suggested Execution Order

### Iteration 1

- Fix diff path normalization.
- Add strict planner/reviewer parsers.
- Add conservative fallback policy.
- Add contract-focused unit tests.

### Iteration 2

- Introduce reviewer registry.
- Remove duplicated reviewer assembly logic.
- Align prompt scope and file filter scope.

### Iteration 3

- Extract framework-agnostic pipeline core.
- Add diagnostics model and structured logging.

### Iteration 4

- Migrate orchestration off deprecated ADK APIs.
- Run compatibility and benchmark regression tests.

## 11. Acceptance Criteria

The refactor should be considered successful when:

- Invalid planner output no longer causes all reviewers to be skipped silently.
- Invalid reviewer output is visible in diagnostics and test results.
- Standard unified diffs always resolve to valid repository file paths for tools.
- Adding a new reviewer requires editing one registry entry plus prompt/domain logic, not multiple disconnected files.
- Core pipeline tests run without depending on deprecated ADK orchestration objects.
- Benchmark recall does not regress while degraded-run visibility improves.

## 12. Short Recommendation

If only one refactor window is available, prioritize:

1. Path normalization.
2. Fail-safe planner and reviewer parsing.
3. Reviewer registry.

These three changes address the largest correctness risks without forcing a full framework migration at the same time.
