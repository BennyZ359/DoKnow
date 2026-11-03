# DoKnow v1 implementation contract

Base `/api`. Single local learner; no public multi-user/auth claims. All API timestamps ISO UTC. Vue frontend uses proxy `/api`.

Resource identifiers are UUID strings. Question identifiers and practice tokens are opaque, unit-local strings. Validation errors return 422 with `{detail:[{loc,msg,type}]}` without echoing learner inputs. Invalid Unicode/NUL strings are rejected. Provider failures return a safe 502 without changing progress. Reflection schedules first recall one day later; early reviews return 409.

## Core endpoints

- `GET /health` -> `{status, mode, database}`.
- `GET /diagnostics` -> `{status: ok|error,mode,database,read_only:true,checks:[{name,status:ok|warning|error|pending,detail,action,revision?,expected_revision?}]}` with `Cache-Control: no-store`. Names are `backend`, `mode`, `database`. HTTP 200 means the report was read, not that every check passed; database/configuration faults appear as checks with error status. Recognized revisions are allowlisted; unknown values are never echoed. No model calls, initialization, migration, learning writes, credentials, connection strings, paths, raw exceptions or learner content. SQLite file inspection uses a temporary main/WAL snapshot to avoid source-side SHM writes; concurrent changes may yield a retryable diagnosis failure. In-memory SQLite uses the existing engine, PostgreSQL uses a read-only transaction. Frontend runtime/dependency and offline port checks are provided by the local CLI, not this endpoint.
- `GET /dashboard` -> `{goals, reviews_due, total_sessions, knowledge_count, recent_activity}`. `goals` contains the goal objects below.
- `GET /goals` -> array of goals. `POST /goals` body `{title, motivation, level: beginner|intermediate|advanced, daily_minutes: 10..180}` -> goal including generated units. `GET /goals/{id}` -> goal. `DELETE /goals/{id}` -> 204.
- Goal: `{id,title,motivation,level,daily_minutes,created_at,updated_at,version,course_version,units:[{id,title,objective,position,archived,stage,mastery,review_due_at,review_count,completed_at}],progress}`. Only active units appear in this list and contribute to progress. Stages `learn`, `practice`, `project`, `teach`, `reflect`, `review`, `complete`. `progress` 0..100.
- `PATCH /goals/{id}` body `{version,title?,motivation?,daily_minutes?}` -> updated goal. A positive integer `version` from the last GET and at least one editable field are required. Title is 2..200 trimmed characters, motivation 0..4,000, and daily_minutes an integer 10..180. Unknown fields (including level and units) and explicit nulls are rejected with 422. This changes only basic goal information: no plan generation or model evaluation; course content, level, ordering, progress, sessions, assessments and review dates are preserved. The name is reflected in current goal/unit headers and future tutor context. Daily time is a planning reference, not a course or review rescheduler.
- `GET /units/{id}` -> unit with `goal_id,goal_title,lesson:{explanation,example,question},practice,project:{title,brief,criteria},teach:{prompt,checklist},sessions:[]`. Practice contains only the active question and progress (see below). Private answer keys, future questions and their explanations MUST NOT be returned; submission feedback explains the answered question.
- `POST /units/{id}/chat` `{message}` -> `{reply,mode}`; messages persisted as sessions (kind chat, content user message, feedback reply).
- `POST /units/{id}/learn` `{reflection}` -> `{unit,feedback}`. At least 20 non-whitespace characters. Advances learn to practice only.
- `POST /units/{id}/practice` `{answer,question_id,token}` -> `{unit,feedback,score,passed,practice_complete,assessment}`. `answer` is the index in the displayed options, encoded as a string (`"0"`, `"1"`, etc.). `passed` describes this attempt; only `practice_complete: true` advances to project. Missing or stale question identity returns 409 without recording an attempt. Existing single-question courses still accept `{answer}`.
- `POST /units/{id}/project` `{content}` -> `{unit,feedback,score,passed,assessment}`. Meaningful project artifact assessed; pass advances teach.
- `POST /units/{id}/teach` `{content}` -> `{unit,feedback,score,passed,assessment}`. Teach-back assessed for conceptual correctness, example, boundary; pass advances reflect.
- `POST /units/{id}/reflect` `{content,takeaway,change}` -> `{unit,feedback}`. Content >=20 and takeaway/change >=10 characters; creates knowledge note and review schedule, advances review.
- `GET /reviews` -> array of unit objects (with goal_title) due now. `POST /units/{id}/review` `{rating: 1|2|3|4,answer}` -> `{unit,feedback,score,passed,assessment}`. Recall assessment limits self-rating; poor recall starts a new practice round, successful recall advances complete and schedules next review. Complete remains eligible for scheduled review. Other stage attempts -> 409. Learner can practice failed review then repeat loop.
- Sessions: `{id,unit_id,kind,content,feedback,score,created_at,assessment}`.

## Course adjustment endpoints

Rules and acceptance scenarios: [COURSE_ADJUSTMENTS.md](COURSE_ADJUSTMENTS.md). Goal `version` remains the metadata-edit version; `course_version` starts at 1 and increases once per confirmed change. The goal level then describes future difficulty; started units keep their original materials.

- `GET /goals/{goal_id}/course` -> `{goal,units,history}`. Units are active summaries `{id,title,objective,position,retained}`. A unit is retained if it has a saved session (including chat), a non-learn stage, mastery, practice state, review/completion record, or linked note. Browsing/local drafts alone do not start a unit. History contains confirmed changes, newest course version first.
- `POST /goals/{goal_id}/course/preview` -> 201 change. Body is exactly `{course_version,kind:"regenerate"}`, `{course_version,kind:"difficulty",level}`, or `{course_version,kind:"reorder",unit_ids}`. Course version is a positive strict integer. Reorder supplies every unstarted ID exactly once; started positions remain fixed. Unknown/extra/null fields, unchanged difficulty/order, duplicate/foreign IDs, or fewer than two movable units for reorder return 422. No unstarted units returns 409.
- Regeneration and difficulty changes replace only unstarted slots, preserving their count. Retained topics are supplied as context. Invalid or wrong-count provider results return 502 without changing the course. Demo uses deterministic templates: regenerating at the same difficulty can reproduce identical materials and does not claim novel AI teaching.
- `GET /goals/{goal_id}/course/previews/{preview_id}` -> stored change, or 404. Restores a browser preview by ID; the server owns the materials.
- Change: `{id,goal_id,kind,base_version,course_version,created_at,applied_at,before:{title,level,units},after:{level,units}}`. Applied time is null before confirmation; course_version is the proposed next version. New units include `replaces` (old ID) and public `lesson,project,teach` for inspection. No answer keys, question banks or internal lock counters appear in preview/history responses. Titles, objectives, order and generated materials are historical snapshots.
- `POST /goals/{goal_id}/course/apply` body `{preview_id,confirmed:true}` -> goal. The boolean must be literal true. Client-supplied materials are forbidden. Preview binds metadata version, course version and all active unit versions. Intervening learning, metadata edits, replacement or reorder return 409 `{code:"course_conflict",detail}`. Fetch current state and generate a new preview; never silently rebase. An already-applied preview also conflicts unless replaying its original receipt.

Replacement uses new IDs; old units retain their material and become `archived:true`. `GET /units/{id}` remains readable; new POSTs to archived units return 409 before any provider call or learning write. Original completed receipts can still replay. Reorder keeps IDs and material. Protected units retain positions, material, progress, sessions, assessments, notes and review dates. Goal deletion cascades to archived units and course changes and erases related receipt bodies; independent notes survive.

Preview generation releases its read transaction during provider requests. Conditional goal/unit UPDATEs check versions and lock rows before preview storage or application. Confirmation, archives, new units, history and the response receipt commit together. No deliberate writer lock is held while awaiting a provider. Unconfirmed previews remain stored until goal deletion and are included in backups; only confirmed ones appear in history.

Both course POSTs support `Idempotency-Key` and the safe retry contract below. Preserve the same path, key and payload after a lost response. The browser stores pending actions and the preview ID; the server restores the actual preview. A confirmed save stays successful if later state synchronization fails.

Provider: `async regenerate_units(title, level, daily_minutes, targets, retained) -> list[dict]` returns the same complete unit shape as generate_plan, with 1-6 units in target order and server-attached question provenance. Context contains title, objective and position, never learner submissions or private answer keys. The route additionally checks exact target count. Provider context and provenance have mock coverage; real provider connectivity remains unverified.

## Practice progress and assessment evidence

Public `practice` is `{question_id,token,question,options,total,correct,remaining,round,attempt,is_retry,legacy}`. New demo units have three questions; AI plans require one primary question plus two to four different scenario variants. An incorrect answer moves that question to the end of the queue; each distinct question must be answered correctly to finish. Options are deterministically reordered for each attempt, remaining stable across reads and restarts. Legacy single-question courses preserve their original option order and material.

`round` and `attempt` are one-based display counters. `round` increments only when failed recall starts new practice, independently of `review_count`. New rounds clear completion and mistake state and rotate the starting question; prior attempt history remains intact. Completed rounds have `question_id: null` and no options. Clients submit the exact question identity and token they displayed, scope drafts to that identity, and refresh after a conflict. Replaying an idempotency receipt returns the original assessment, without grading the next question.

Each scored session stores an `assessment` snapshot. `source` is `demo` (structural check), `ai` (model evaluation), `answer_key` (server-side choice grading), or `unknown`. New evidence includes `passed` and the relevant `rule_version`, `provider`, `requested_model`, and response `model`; absent model information is null, not inferred from later settings. Legacy scored records return `{source:"unknown"}`; unscored records have null assessment.

Choice assessments additionally store `question_id`, `question`, displayed `options`, `selected_answer`, `correct_answer`, `round`, `attempt`, `was_retry`, and `question_source` (the question bank provenance). Only the submitted question's answer is disclosed. Review assessments preserve both `evaluation_passed` and `self_rating`; `passed` reflects the final progression decision, including a self-rating of 1 requiring further practice. No credentials, base URLs, or raw provider responses are stored in provenance.

## Knowledge endpoints

- `GET /knowledge` -> array `{id,title,content,source,created_at,updated_at,version,tags}`. Optional `q` (up to 4,000 characters) searches title, current body and tags; `tag` (up to 40 characters) matches a whole tag; `source` is `note|reflection|import`. Filters combine with AND, text/tag matching ignores case and surrounding whitespace. No filters returns all entries in creation order, newest first.
- `GET /knowledge/{id}` -> entry plus `original:{title,content}`. Before the first edit, original is the current record; on the first edit it is captured in the same transaction and remains unchanged thereafter. For migrated notes this is the retained pre-edit content, not an invented reconstruction of earlier history. Learning sessions and assessment evidence are never edited by this endpoint. Independent notes and their original snapshots survive goal deletion.
- `POST /knowledge` JSON `{title,content,tags?}` -> entry, source `note`, content 10..1,000,000 characters with at least 10 non-whitespace characters. Tags default to `[]`; max 20 strings of 1..40 trimmed characters. Duplicates ignoring case are collapsed (first spelling retained); invalid Unicode, NUL, control characters and empty tags are rejected.
- `PATCH /knowledge/{id}` JSON `{version,title?,content?,tags?}` -> detailed entry. Requires a positive integer version and at least one editable field; explicit nulls and unknown fields are rejected. `tags: []` removes all tags. Source, creation date, original snapshot and linked learning evidence are not editable. Every successful PATCH, including an unchanged payload, increments the version and updates the timestamp.
- `GET /knowledge/{id}/export` -> UTF-8 `text/markdown` attachment `doknow-note.md`. `GET /knowledge/export` accepts the same filters as the list and returns `doknow-knowledge.md`, including a readable empty result. Exports include current Markdown body, tags, source, timestamps and version; changed title/body also includes the retained original. Metadata is escaped as literal Markdown; body Markdown is preserved. Export reads only note fields and never includes application configuration, credentials or receipt internals.
- `POST /knowledge/import` multipart `file` -> entry; .md/.txt/.pdf/.docx, max 10 MB, extracted text max200k characters, PDF max200pages, DOCX expansion max25MB, no file paths exposed.
- `DELETE /knowledge/{id}` -> 204.
- `POST /knowledge/ask` `{question}` -> `{answer,sources:[{id,title,excerpt}],mode}`. Retrieval uses all current local notes, independent of list filters, and never the retained original snapshots. No sources means explicitly insufficient materials. Cache keys include current title, body, revision and provider; saved edits and deletions make old cached answers unreachable. A change during an in-flight model/cache read returns 409 `{code:"knowledge_changed",detail}` so the client can ask again against current materials. Old cache entries expire after 10 minutes; Redis is optional.
- `GET /settings` -> `{mode,provider,model,configured,principles:[{name,practice}],limitations:[]}`. Never return API keys or connection strings. Provider is allowlisted (`unknown` for an invalid setting); credential-like model names are hidden. `configured` means local configuration validation, not verified model connectivity.

## Provider module contract (pure service layer)

`app.services.learning`:
- `async generate_plan(title: str, level: str, daily_minutes: int) -> list[dict]` (3-6 units each `{title,objective,lesson:{explanation,example,question},practice:{question,options,correct_index,explanation},practice_variants:[practice,...],question_source,project:{title,brief,criteria},teach:{prompt,checklist}}`). Variants contain 2-4 distinct question prompts; question provenance is attached server-side after provider validation.
- `async tutor_reply(goal_title: str, unit: dict, message: str, history: list[dict]) -> dict` `{reply,mode}`.
- `async evaluate_submission(kind: str, unit: dict, content: str) -> dict` `{score:0..100,passed:bool,feedback:str,provenance}`. kind project, teach, review; pass threshold 70; demo checks structure only. Provenance is captured from the configuration used for that request and the provider's response model field, not generated by the model's assessment text.
- `provider_status() -> dict` `{mode,provider,model,configured,limitations}`.

`app.services.knowledge`:
- `extract_document(filename: str, data: bytes) -> str` raises ValueError on unsupported/empty/oversized.
- `async answer_question(question: str, documents: list[dict]) -> dict` `{answer,sources:[{id,title,excerpt}],mode}`. Documents have id,title,content.

Provider reads environment via `os.getenv`; backend settings env: `DATABASE_URL` default sqlite:///./data/doknow.db, `AI_PROVIDER` demo|openai|compatible, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`, `CORS_ORIGINS`. Services must work with demo default and fail safely on AI errors. Env loading via backend dotenv at boot.

## Safe write retries

The client may send `Idempotency-Key` on `POST /goals`, course preview/apply POSTs, every `POST /units/{id}/...`, `POST /knowledge`, `POST /knowledge/import`, `PATCH /goals/{id}`, and `PATCH /knowledge/{id}`. Use a random UUID for each deliberate user action (accepted syntax: 8–128 ASCII letters, digits, `.`, `_`, `:`, or `-`). Keep the same key, method, version and payload when retrying after a lost response; changed content or an explicitly reconciled new version uses a new key. Clients without the header still have mandatory version protection on PATCH. `POST /knowledge/ask` and DELETE requests are outside this receipt mechanism.

Edits use optimistic concurrency at both the displayed version check and the database UPDATE. A stale version or competing committed update returns 409 `{code:"edit_conflict",detail}` without modifying the record. Fetch the latest record, retain local input, compare/merge, and only then submit its new version. The UI does not automatically replace the version after a conflict. Edit drafts retain their base version across reloads; failed synchronization or replay of an earlier save cannot clear newer unsaved text. Goal versions cover basic information only, so learning activity can continue without invalidating an unrelated metadata edit.

A successful HTTP response, including a failed assessment returned as HTTP 200, is stored with the business data in one transaction. Replaying the same method, path, and payload returns that original status and JSON body with `Idempotency-Replayed: true`; the first successful response has `false`. Replaying never duplicates a committed goal, note, session, review count, or model evaluation. Receipts survive application restarts and are included in database backups. There is no time-based receipt expiry in this version; resource deletion erases associated response bodies as described below.

The fingerprint ignores JSON whitespace and object key order. For imports it uses the normalized basename and actual file bytes, so a different multipart boundary does not create a different request. It does not contain API keys or store raw request bodies. The saved response can contain the same learning content already present in the normal API response.

| HTTP status / `code` | Client action |
| --- | --- |
| 409 / `idempotency_in_progress` | The same action is running; retain the key and retry after the `Retry-After` interval (2 seconds). |
| 409 / `idempotency_conflict` | The key belongs to a different path or payload; reconcile saved records before starting a new action. |
| 409 / `idempotency_expired_owner` | Another recovery request took ownership; retain the key and synchronize/retry. |
| 503 / `idempotency_storage_busy` | Storage is temporarily unavailable; retain the key and retry later. |
| 410 / `idempotency_resource_deleted` | The related goal or note was deleted; discard the pending operation and do not recreate it automatically. |
| 422 / `idempotency_invalid_key` | Generate a valid action identifier. |

These errors return `{detail: string, code: string}`. Normal validation, stage conflicts, and model errors retain their original response format. Requests that fail before commit release their receipt lease and can be retried. An abandoned in-flight lease can be reclaimed after 120 seconds. The final ownership check prevents an older worker from committing after takeover. No database writer lock is deliberately held while awaiting the model.

A receipt is a historical response, so the client should apply the confirmed success, then refresh current state without repeating the write. A later unit GET or dashboard refresh failing does not undo the successful POST. A replay can describe an older stage of an existing resource. Deleting a goal or note atomically erases the response bodies retained for that resource and leaves only a tombstone (key, fingerprint, ownership/timing metadata and resource identifier). Replaying its key returns 410 without returning deleted content or recreating data. Deleting a goal still preserves independent reflection notes as documented by the original delete endpoint.

External model execution and database commits cannot be one transaction: if a process dies after the model responds but before the database commits, recovery may call the model again. The guarantees concern committed learning data and completed response replays, not exactly-once model billing.

Cross-origin local clients can send `Idempotency-Key` with POST or PATCH; CORS exposes `Idempotency-Replayed` and `Retry-After`.

## Ownership

Backend agent: backend/app excluding services/, backend/tests core tests; owns schemas/models/routes/database. Frontend agent: frontend/ only. Intelligence agent: backend/app/services/ and backend/tests/test_services.py only. Root: configuration, dependencies, deployment, docs, integration/E2E and final fixes.
