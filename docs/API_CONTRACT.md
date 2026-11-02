# DoKnow v1 implementation contract

Base `/api`. Single local learner; no public multi-user/auth claims. All API timestamps ISO UTC. Vue frontend uses proxy `/api`.

All identifiers are UUID strings. Validation errors return 422 with `{detail:[{loc,msg,type}]}` without echoing learner inputs. Invalid Unicode/NUL strings are rejected. Provider failures return a safe 502 without changing progress. Reflection schedules first recall one day later; early reviews return 409.

## Core endpoints

- `GET /health` -> `{status, mode, database}`.
- `GET /dashboard` -> `{goals, reviews_due, total_sessions, knowledge_count, recent_activity}`. `goals` contains the goal objects below.
- `GET /goals` -> array of goals. `POST /goals` body `{title, motivation, level: beginner|intermediate|advanced, daily_minutes: 10..180}` -> goal including generated units. `GET /goals/{id}` -> goal. `DELETE /goals/{id}` -> 204.
- Goal: `{id,title,motivation,level,daily_minutes,created_at,units:[{id,title,objective,position,stage,mastery,review_due_at,review_count,completed_at}],progress}`. Stages `learn`, `practice`, `project`, `teach`, `reflect`, `review`, `complete`. `progress` 0..100.
- `GET /units/{id}` -> unit with `goal_id,goal_title,lesson:{explanation,example,question},practice:{question,options,correct_index,explanation},project:{title,brief,criteria},teach:{prompt,checklist},sessions:[]`. Practice correct_index MUST NOT be returned; assessment occurs server-side.
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

## Ownership

Backend agent: backend/app excluding services/, backend/tests core tests; owns schemas/models/routes/database. Frontend agent: frontend/ only. Intelligence agent: backend/app/services/ and backend/tests/test_services.py only. Root: configuration, dependencies, deployment, docs, integration/E2E and final fixes.
