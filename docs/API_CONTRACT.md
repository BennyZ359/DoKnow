# DoKnow v1 implementation contract

Base `/api`. Single local learner; no public multi-user/auth claims. All API timestamps ISO UTC. Vue frontend uses proxy `/api`.

All identifiers are UUID strings. Validation errors return 422 with `{detail:[{loc,msg,type}]}` without echoing learner inputs. Invalid Unicode/NUL strings are rejected. Provider failures return a safe 502 without changing progress. Reflection schedules first recall one day later; early reviews return 409.

## Core endpoints

- `GET /health` -> `{status, mode, database}`.
- `GET /dashboard` -> `{goals, reviews_due, total_sessions, knowledge_count, recent_activity}`. `goals` contains the goal objects below.
- `GET /goals` -> array of goals. `POST /goals` body `{title, motivation, level: beginner|intermediate|advanced, daily_minutes: 10..180}` -> goal including generated units. `GET /goals/{id}` -> goal. `DELETE /goals/{id}` -> 204.
- Goal: `{id,title,motivation,level,daily_minutes,created_at,units:[{id,title,objective,position,stage,mastery,review_due_at,review_count,completed_at}],progress}`. Stages `learn`, `practice`, `project`, `teach`, `reflect`, `review`, `complete`. `progress` 0..100.
- `GET /units/{id}` -> unit with `goal_id,goal_title,lesson:{explanation,example,question},practice:{question,options},project:{title,brief,criteria},teach:{prompt,checklist},sessions:[]`. Practice `correct_index` and the answer explanation MUST NOT be returned; assessment occurs server-side and the submission feedback supplies its explanation.
- `POST /units/{id}/chat` `{message}` -> `{reply,mode}`; messages persisted as sessions (kind chat, content user message, feedback reply).
- `POST /units/{id}/learn` `{reflection}` -> `{unit,feedback}`. At least 20 non-whitespace characters. Advances learn to practice only.
- `POST /units/{id}/practice` `{answer}` -> `{unit,feedback,score,passed}`. answer string, multiple-choice index `0`, `1`, etc. Fail keeps practice; pass advances project. Repeat safe stage gating.
- `POST /units/{id}/project` `{content}` -> `{unit,feedback,score,passed}`. Meaningful project artifact assessed; pass advances teach.
- `POST /units/{id}/teach` `{content}` -> `{unit,feedback,score,passed}`. Teach-back assessed for conceptual correctness, example, boundary; pass advances reflect.
- `POST /units/{id}/reflect` `{content,takeaway,change}` -> `{unit,feedback}`. Content >=20 and takeaway/change >=10 characters; creates knowledge note and review schedule, advances review.
- `GET /reviews` -> array of unit objects (with goal_title) due now. `POST /units/{id}/review` `{rating: 1|2|3|4,answer}` -> `{unit,feedback,score,passed}`. Recall assessment limits self-rating; poor recall returns practice, successful recall advances complete and schedules next review. Complete remains eligible for scheduled review. Other stage attempts -> 409. Learner can practice failed review then repeat loop.
- Sessions: `{id,unit_id,kind,content,feedback,score,created_at}`.

## Knowledge endpoints

- `GET /knowledge` -> array `{id,title,content,source,created_at}`.
- `POST /knowledge` JSON `{title,content}` -> entry, source `note`, content 10..1,000,000 characters.
- `POST /knowledge/import` multipart `file` -> entry; .md/.txt/.pdf/.docx, max 10 MB, extracted text max200k characters, PDF max200pages, DOCX expansion max25MB, no file paths exposed.
- `DELETE /knowledge/{id}` -> 204.
- `POST /knowledge/ask` `{question}` -> `{answer,sources:[{id,title,excerpt}],mode}`. Retrieval scoped to this local learner. No sources means explicitly insufficient materials.
- `GET /settings` -> `{mode,provider,model,configured,principles:[{name,practice}],limitations:[]}`. Never return API keys.

## Provider module contract (pure service layer)

`app.services.learning`:
- `async generate_plan(title: str, level: str, daily_minutes: int) -> list[dict]` (3-6 units each `{title,objective,lesson:{explanation,example,question},practice:{question,options,correct_index,explanation},project:{title,brief,criteria},teach:{prompt,checklist}}`).
- `async tutor_reply(goal_title: str, unit: dict, message: str, history: list[dict]) -> dict` `{reply,mode}`.
- `async evaluate_submission(kind: str, unit: dict, content: str) -> dict` `{score:0..100,passed:bool,feedback:str}`. kind project, teach, review; pass threshold 70; demo score conservative, does not pretend AI judgment.
- `provider_status() -> dict` `{mode,provider,model,configured,limitations}`.

`app.services.knowledge`:
- `extract_document(filename: str, data: bytes) -> str` raises ValueError on unsupported/empty/oversized.
- `async answer_question(question: str, documents: list[dict]) -> dict` `{answer,sources:[{id,title,excerpt}],mode}`. Documents have id,title,content.

Provider reads environment via `os.getenv`; backend settings env: `DATABASE_URL` default sqlite:///./data/doknow.db, `AI_PROVIDER` demo|openai|compatible, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`, `CORS_ORIGINS`. Services must work with demo default and fail safely on AI errors. Env loading via backend dotenv at boot.

## Safe write retries

The client may send `Idempotency-Key` on `POST /goals`, every `POST /units/{id}/...`, `POST /knowledge`, and `POST /knowledge/import`. Use a random UUID for each deliberate user action (accepted syntax: 8–128 ASCII letters, digits, `.`, `_`, `:`, or `-`). Keep the same key when retrying that action after a lost response; a changed payload or a deliberate new attempt uses a new key. Clients without the header keep the original API behavior. `POST /knowledge/ask` and DELETE requests are outside this receipt mechanism.

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

Cross-origin local clients can send `Idempotency-Key`; CORS exposes `Idempotency-Replayed` and `Retry-After`.

## Ownership

Backend agent: backend/app excluding services/, backend/tests core tests; owns schemas/models/routes/database. Frontend agent: frontend/ only. Intelligence agent: backend/app/services/ and backend/tests/test_services.py only. Root: configuration, dependencies, deployment, docs, integration/E2E and final fixes.
