"""HTTP API for an evidence-based learn → do → teach → review cycle."""

from contextlib import asynccontextmanager
from datetime import timedelta, timezone
import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from .database import make_database
from .editing import EditConflict, export_note, filter_notes, require_version
from .migrations import initialize_database
from .cache import AnswerCache, answer_key
from .idempotency import DEFER_COMMIT, IdempotentRoute, erase_receipts
from .models import Goal, KnowledgeEntry, LearningSession, Unit, now_utc
from .practice import StalePractice, grade_practice, restart_practice
from .schemas import ChatInput, GoalInput, GoalUpdate, KnowledgeInput, KnowledgeUpdate, LearnInput, PracticeInput, QuestionInput, ReflectionInput, ReviewInput, SubmissionInput
from .serialization import goal_data, knowledge_data, session_data, unit_data
from .services.knowledge import answer_question, extract_document
from .services.learning import evaluate_submission, generate_plan, provider_status, tutor_reply
from .services.providers import ProviderError

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PRINCIPLES = [
    {"name": "知行合一", "practice": "理解以后提交实践证据，让行动检验知识。"},
    {"name": "学而时习之", "practice": "结合间隔重复与主动回忆，在适当时间重新检验。"},
    {"name": "学思结合", "practice": "先说出自己的理解，再通过导师追问澄清误区。"},
    {"name": "学不可以已", "practice": "完成一轮仍安排复习，以持续证据观察成长。"},
    {"name": "格物致知", "practice": "从具体问题、输入与结果中寻找原理和适用边界。"},
    {"name": "闻思修", "practice": "听闻讲解、独立思考、亲自练习，并不断回看。"},
    {"name": "教学做合一", "practice": "实战以后讲给别人听，用例子与边界检验表达。"},
]


def get_db(request: Request):
    owned = getattr(request.state, "idempotency_session", None)
    if owned is not None:
        yield owned
        return
    with request.app.state.session_factory() as session:
        yield session


DB = Annotated[Session, Depends(get_db)]


def get_unit(db: Session, unit_id: str) -> Unit:
    item = db.scalar(select(Unit).where(Unit.id == unit_id).options(selectinload(Unit.goal), selectinload(Unit.sessions)))
    if item is None:
        raise HTTPException(404, "没有找到这个学习单元。")
    return item


def require_stage(unit: Unit, *allowed: str):
    if unit.stage not in allowed:
        raise HTTPException(409, f"当前阶段为 {unit.stage}，请按学习证据完成前面的阶段。")


def record(db: Session, unit: Unit, kind: str, content: str, feedback: str, score: int | None = None,
           evaluation: dict | None = None):
    unit.updated_at = now_utc()
    evidence = LearningSession(unit=unit, kind=kind, content=content, feedback=feedback, score=score,
                               assessment=evaluation)
    db.add(evidence)


def save(db: Session, *, editing: bool = False):
    try:
        if db.info.get(DEFER_COMMIT):
            db.flush()
        else:
            db.commit()
    except StaleDataError:
        db.rollback()
        if editing:
            raise EditConflict
        raise HTTPException(409, "这个学习单元刚刚更新，请刷新后继续，避免重复提交。")


def internal_unit(unit: Unit) -> dict:
    # The private answer key goes only to grading services, never to API consumers.
    return {**unit_data(unit), **unit.material}


def assessment(value: dict) -> tuple[int, bool, str]:
    try:
        score = max(0, min(100, int(value["score"])))
        feedback = str(value["feedback"]).strip()
        if not feedback:
            raise ValueError("missing feedback")
        return score, score >= 70 and value.get("passed") is True, feedback
    except (KeyError, TypeError, ValueError):
        raise HTTPException(502, "评估服务返回了不完整结果，请稍后重试；本次没有记录学习进度。")


def assessment_evidence(value: dict, passed: bool) -> dict:
    provenance = value.get("provenance") or {"source": "unknown"}
    return {key: provenance.get(key) for key in ("source", "provider", "model", "requested_model", "rule_version")} | {"passed": passed}


def validate_plan(plan: list[dict]):
    try:
        if not isinstance(plan, list) or not 3 <= len(plan) <= 6:
            raise ValueError("unit count")
        for unit in plan:
            if not isinstance(unit, dict):
                raise ValueError("unit")
            if not unit.get("title") or len(unit["title"]) > 200 or not unit.get("objective"):
                raise ValueError("title/objective")
            for name in ("lesson", "practice", "project", "teach"):
                if not isinstance(unit.get(name), dict):
                    raise ValueError(name)
            practice = unit["practice"]
            options = practice["options"]
            correct = practice["correct_index"]
            if not isinstance(options, list) or not 2 <= len(options) <= 8:
                raise ValueError("options")
            if type(correct) is not int or not 0 <= correct < len(options):
                raise ValueError("answer")
            if not all(isinstance(option, str) and option.strip() for option in options):
                raise ValueError("option text")
            if "practice_variants" in unit:
                from .services.learning import PlanUnit
                PlanUnit.model_validate({key: value for key, value in unit.items() if key != "question_source"})
    except (KeyError, TypeError, ValueError):
        raise HTTPException(502, "学习规划服务返回了不完整计划，请重试；本次没有创建目标。")


def create_app(database_url: str | None = None) -> FastAPI:
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/doknow.db")
    engine, session_factory = make_database(database_url)
    answer_cache = AnswerCache(os.getenv("REDIS_URL") or None)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            initialize_database(engine)
            yield
        finally:
            await answer_cache.close()
            engine.dispose()

    application = FastAPI(
        title="DoKnow API", version="0.1.0", lifespan=lifespan,
        description="A local learning companion: knowledge becomes capability through practice, teaching and recall.",
    )
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.router.route_class = IdempotentRoute
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
        allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["Idempotency-Replayed", "Retry-After"],
    )

    @application.exception_handler(ProviderError)
    async def provider_failure(_: Request, error: ProviderError):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @application.exception_handler(EditConflict)
    async def edit_conflict(_: Request, error: EditConflict):
        return JSONResponse(status_code=409, content={
            "detail": "这条记录已在其他页面更新。你的修改尚未保存，请核对最新内容后再保存。",
            "code": "edit_conflict",
        })

    @application.exception_handler(RequestValidationError)
    async def validation_failure(_: Request, error: RequestValidationError):
        # Avoid echoing large learner submissions or invalid Unicode into JSON.
        details = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @application.get("/api/health")
    def health(db: DB):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "mode": provider_status()["mode"], "database": engine.dialect.name}

    @application.get("/api/settings")
    def settings():
        status = provider_status()
        # Explicit whitelist protects any future provider metadata changes.
        return {key: status.get(key) for key in ("mode", "provider", "model", "configured", "limitations")} | {"principles": PRINCIPLES}

    @application.get("/api/dashboard")
    def dashboard(db: DB):
        goals = db.scalars(select(Goal).order_by(Goal.created_at.desc()).options(selectinload(Goal.units))).all()
        due = db.scalar(select(func.count()).select_from(Unit).where(Unit.stage.in_(("review", "complete")), Unit.review_due_at <= now_utc()))
        activity = db.scalars(select(LearningSession).order_by(LearningSession.created_at.desc()).limit(8)).all()
        return {"goals": [goal_data(goal) for goal in goals], "reviews_due": due or 0,
                "total_sessions": db.scalar(select(func.count()).select_from(LearningSession)) or 0,
                "knowledge_count": db.scalar(select(func.count()).select_from(KnowledgeEntry)) or 0,
                "recent_activity": [session_data(item) for item in activity]}

    @application.get("/api/goals")
    def list_goals(db: DB):
        items = db.scalars(select(Goal).order_by(Goal.created_at.desc()).options(selectinload(Goal.units))).all()
        return [goal_data(item) for item in items]

    @application.post("/api/goals", status_code=201)
    async def create_goal(body: GoalInput, db: DB):
        plan = await generate_plan(body.title, body.level, body.daily_minutes)
        validate_plan(plan)
        item = Goal(**body.model_dump())
        for position, material in enumerate(plan):
            item.units.append(Unit(title=material["title"], objective=material["objective"], position=position,
                                   material={name: material[name] for name in (
                                       "lesson", "practice", "practice_variants", "question_source", "project", "teach"
                                   ) if name in material}))
        db.add(item)
        save(db)
        return goal_data(item)

    @application.get("/api/goals/{goal_id}")
    def fetch_goal(goal_id: str, db: DB):
        item = db.scalar(select(Goal).where(Goal.id == goal_id).options(selectinload(Goal.units)))
        if item is None:
            raise HTTPException(404, "没有找到这个学习目标。")
        return goal_data(item)

    @application.patch("/api/goals/{goal_id}")
    def update_goal(goal_id: str, body: GoalUpdate, db: DB):
        item = db.scalar(select(Goal).where(Goal.id == goal_id).options(selectinload(Goal.units)))
        if item is None:
            raise HTTPException(404, "没有找到这个学习目标。")
        require_version(item, body.version)
        for name, value in body.model_dump(exclude_unset=True, exclude={"version"}).items():
            setattr(item, name, value)
        item.version += 1
        item.updated_at = now_utc()
        save(db, editing=True)
        return goal_data(item)

    @application.delete("/api/goals/{goal_id}", status_code=204)
    def delete_goal(goal_id: str, db: DB):
        item = db.get(Goal, goal_id)
        if item is None:
            raise HTTPException(404, "没有找到这个学习目标。")
        db.delete(item)
        erase_receipts(db, f"goal:{goal_id}")
        save(db)
        return Response(status_code=204)

    @application.get("/api/units/{unit_id}")
    def fetch_unit(unit_id: str, db: DB):
        return unit_data(get_unit(db, unit_id), detailed=True)

    @application.post("/api/units/{unit_id}/chat")
    async def chat(unit_id: str, body: ChatInput, db: DB):
        unit = get_unit(db, unit_id)
        history = [session_data(session) for session in unit.sessions][-10:]
        result = await tutor_reply(unit.goal.title, internal_unit(unit), body.message, history)
        reply = result.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            raise HTTPException(502, "导师暂时没有返回完整回复，请重试。")
        record(db, unit, "chat", body.message, reply)
        save(db)
        return {"reply": reply, "mode": result.get("mode", provider_status()["mode"])}

    @application.post("/api/units/{unit_id}/learn")
    def learn(unit_id: str, body: LearnInput, db: DB):
        unit = get_unit(db, unit_id)
        require_stage(unit, "learn")
        unit.stage = "practice"
        unit.mastery = 10
        feedback = "已记录你的理解。现在先独立作答，通过练习检验这些想法。"
        record(db, unit, "learn", body.reflection, feedback)
        save(db)
        return {"unit": unit_data(unit, detailed=True), "feedback": feedback}

    @application.post("/api/units/{unit_id}/practice")
    def practice(unit_id: str, body: PracticeInput, db: DB):
        unit = get_unit(db, unit_id)
        require_stage(unit, "practice")
        try:
            result = grade_practice(unit, body.answer, body.question_id, body.token)
        except StalePractice as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if result["complete"]:
            unit.stage = "project"
            unit.mastery = 35
        elif not result["passed"]:
            unit.mastery = min(unit.mastery, 10)
        record(db, unit, "practice", result["assessment"]["selected_answer"], result["feedback"],
               result["score"], result["assessment"])
        save(db)
        return {"unit": unit_data(unit, detailed=True), "feedback": result["feedback"], "score": result["score"],
                "passed": result["passed"], "practice_complete": result["complete"], "assessment": result["assessment"]}

    async def submit(unit_id: str, body: SubmissionInput, db: Session, kind: str, next_stage: str, mastery: int):
        unit = get_unit(db, unit_id)
        require_stage(unit, kind)
        evaluation = await evaluate_submission(kind, internal_unit(unit), body.content)
        score, passed, feedback = assessment(evaluation)
        evidence = assessment_evidence(evaluation, passed)
        if passed:
            unit.stage = next_stage
            unit.mastery = mastery
        record(db, unit, kind, body.content, feedback, score, evidence)
        save(db)
        return {"unit": unit_data(unit, detailed=True), "feedback": feedback, "score": score, "passed": passed,
                "assessment": evidence}

    @application.post("/api/units/{unit_id}/project")
    async def project(unit_id: str, body: SubmissionInput, db: DB):
        return await submit(unit_id, body, db, "project", "teach", 60)

    @application.post("/api/units/{unit_id}/teach")
    async def teach(unit_id: str, body: SubmissionInput, db: DB):
        return await submit(unit_id, body, db, "teach", "reflect", 80)

    @application.post("/api/units/{unit_id}/reflect")
    def reflect(unit_id: str, body: ReflectionInput, db: DB):
        unit = get_unit(db, unit_id)
        require_stage(unit, "reflect")
        unit.stage = "review"
        unit.mastery = 85
        unit.completed_at = None
        unit.review_due_at = now_utc() + timedelta(days=1)
        feedback = "已保存复盘与新认识，并安排明天的主动回忆。真正的掌握要经过时间检验。"
        content = f"复盘\n{body.content}\n\n我的沉淀\n{body.takeaway}\n\n体验与认识的变化\n{body.change}"
        note = KnowledgeEntry(title=f"{unit.title} · 学习沉淀"[:200], content=content, source="reflection", unit_id=unit.id)
        db.add(note)
        record(db, unit, "reflect", content, feedback)
        save(db)
        return {"unit": unit_data(unit, detailed=True), "feedback": feedback}

    @application.get("/api/reviews")
    def list_reviews(db: DB):
        items = db.scalars(select(Unit).where(Unit.stage.in_(("review", "complete")), Unit.review_due_at <= now_utc())
                           .order_by(Unit.review_due_at).options(selectinload(Unit.goal))).all()
        return [unit_data(item) for item in items]

    @application.post("/api/units/{unit_id}/review")
    async def review(unit_id: str, body: ReviewInput, db: DB):
        unit = get_unit(db, unit_id)
        require_stage(unit, "review", "complete")
        due = unit.review_due_at
        if due is None or (due.replace(tzinfo=timezone.utc) if due.tzinfo is None else due.astimezone(timezone.utc)) > now_utc():
            raise HTTPException(409, "还没有到复习时间。请让知识经过间隔，再独立回忆。")
        evaluation = await evaluate_submission("review", internal_unit(unit), body.answer)
        score, recalled, feedback = assessment(evaluation)
        passed = recalled and body.rating > 1
        unit.review_count += 1
        if passed:
            unit.review_streak += 1
            intervals = [1, 3, 7, 14, 30, 60]
            interval = intervals[min(unit.review_streak, len(intervals) - 1)]
            if body.rating == 2:
                interval = max(1, interval // 2)
            elif body.rating == 4 and score >= 90:
                interval = min(90, interval + max(1, interval // 2))
            unit.review_due_at = now_utc() + timedelta(days=interval)
            unit.stage = "complete"
            unit.mastery = max(70, min(score, 100))
            unit.completed_at = now_utc()
            feedback += f"\n\n本轮主动回忆已完成，{interval} 天后再回忆一次。"
        else:
            unit.review_streak = 0
            unit.stage = "practice"
            restart_practice(unit)
            unit.mastery = min(score, 35)
            unit.completed_at = None
            unit.review_due_at = None
            feedback += "\n\n回忆证据或你的自评表明仍需巩固，已回到练习。用新的实践再建立理解。"
        content = f"自评：{body.rating}/4\n{body.answer}"
        evidence = {**assessment_evidence(evaluation, passed), "evaluation_passed": recalled, "self_rating": body.rating}
        record(db, unit, "review", content, feedback, score, evidence)
        save(db)
        return {"unit": unit_data(unit, detailed=True), "feedback": feedback, "score": score, "passed": passed,
                "assessment": evidence}

    @application.get("/api/knowledge")
    def list_knowledge(db: DB, q: Annotated[str, Query(max_length=4000)] = "",
                       tag: Annotated[str, Query(max_length=40)] = "",
                       source: Literal["", "note", "reflection", "import"] = ""):
        items = db.scalars(select(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc())).all()
        return [knowledge_data(item) for item in filter_notes(items, q, tag, source)]

    @application.get("/api/knowledge/export")
    def export_knowledge(db: DB, q: Annotated[str, Query(max_length=4000)] = "",
                         tag: Annotated[str, Query(max_length=40)] = "",
                         source: Literal["", "note", "reflection", "import"] = ""):
        items = db.scalars(select(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc())).all()
        content = "\n---\n\n".join(export_note(item) for item in filter_notes(items, q, tag, source))
        return Response(content or "# 知识笔记\n\n没有符合筛选条件的笔记。\n", media_type="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="doknow-knowledge.md"'})

    def get_note(db: Session, entry_id: str) -> KnowledgeEntry:
        item = db.get(KnowledgeEntry, entry_id)
        if item is None:
            raise HTTPException(404, "没有找到这条知识记录。")
        return item

    @application.get("/api/knowledge/{entry_id}")
    def fetch_knowledge(entry_id: str, db: DB):
        return knowledge_data(get_note(db, entry_id), detailed=True)

    @application.get("/api/knowledge/{entry_id}/export")
    def export_one_note(entry_id: str, db: DB):
        return Response(export_note(get_note(db, entry_id)), media_type="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="doknow-note.md"'})

    @application.patch("/api/knowledge/{entry_id}")
    def update_knowledge(entry_id: str, body: KnowledgeUpdate, db: DB):
        item = get_note(db, entry_id)
        require_version(item, body.version)
        if item.original is None:
            item.original = {"title": item.title, "content": item.content}
        for name, value in body.model_dump(exclude_unset=True, exclude={"version"}).items():
            setattr(item, name, value)
        item.version += 1
        item.updated_at = now_utc()
        save(db, editing=True)
        return knowledge_data(item, detailed=True)

    @application.post("/api/knowledge", status_code=201)
    def create_knowledge(body: KnowledgeInput, db: DB):
        item = KnowledgeEntry(**body.model_dump(), source="note")
        db.add(item)
        save(db)
        return knowledge_data(item)

    @application.post("/api/knowledge/import", status_code=201)
    async def import_knowledge(db: DB, file: UploadFile = File(...)):
        limit = 10 * 1024 * 1024
        data = await file.read(limit + 1)
        await file.close()
        if len(data) > limit:
            raise HTTPException(413, "资料不能超过 10 MB。")
        filename = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
        try:
            filename.encode("utf-8")
            if "\x00" in filename:
                raise ValueError("invalid filename")
        except (UnicodeEncodeError, ValueError):
            raise HTTPException(422, "资料文件名包含无效字符，请重命名后导入。")
        try:
            content = await run_in_threadpool(extract_document, filename, data)
        except ValueError as error:
            raise HTTPException(422, str(error))
        if not content.strip():
            raise HTTPException(422, "资料中没有可提取的文字。")
        if len(content) > 1000000:
            raise HTTPException(413, "资料提取后的文字过长，请拆成较小文档。")
        item = KnowledgeEntry(title=Path(filename).stem[:200] or "导入资料", content=content, source=filename[:255])
        db.add(item)
        save(db)
        return knowledge_data(item)

    @application.post("/api/knowledge/ask")
    async def ask_knowledge(body: QuestionInput, db: DB):
        items = db.scalars(select(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc())).all()
        documents = [knowledge_data(item) for item in items]
        provider = provider_status()
        key = answer_key(body.question, documents, provider)
        cached = await answer_cache.get(key)
        result = cached if cached is not None else await answer_question(body.question, documents)
        # A different page may edit while a model/cache request is in flight.
        # Read in a new transaction; never publish an answer to superseded notes.
        with session_factory() as fresh:
            current = [knowledge_data(item) for item in fresh.scalars(select(KnowledgeEntry)).all()]
        if key != answer_key(body.question, current, provider):
            return JSONResponse(status_code=409, content={
                "detail": "资料在回答期间已更新，请根据最新笔记重新提问。", "code": "knowledge_changed",
            })
        if cached is None:
            await answer_cache.put(key, result)
        return result

    @application.delete("/api/knowledge/{entry_id}", status_code=204)
    def delete_knowledge(entry_id: str, db: DB):
        item = db.get(KnowledgeEntry, entry_id)
        if item is None:
            raise HTTPException(404, "没有找到这条知识记录。")
        db.delete(item)
        erase_receipts(db, f"knowledge:{entry_id}")
        save(db)
        return Response(status_code=204)

    return application


app = create_app()
