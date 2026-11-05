"""Chinese prompt vocabulary for every AI role (whitepaper §4–§10).

Prompts are data, not code: each agent node formats a prompt with the facts it
gathered from the service layer and expects a JSON reply shaped by the
``SCHEMA_*`` hints (passed to ``LLMClient.chat_json`` so the model also sees a
machine-readable structure contract).

Hard rules encoded everywhere (whitepaper §6, §12):
- never invent learner data — analyze only from the provided facts;
- distinguish facts from guesses: memory writes must carry an honest
  ``source`` (USER_INPUT / SYSTEM_FACT / AI_ASSESSMENT / AI_GUESS) and
  ``confidence``;
- high-priority problems get high-cost actions (adjust the plan), low-priority
  ones get lightweight actions (a message) (§7);
- anything the learner must confirm (pausing a goal, changing the path) is
  proposed, never executed (§2 human-in-the-loop).
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Shared persona preamble — the six principles (whitepaper §2)
# --------------------------------------------------------------------------

PRINCIPLES = """你是 DoKnow 系统中的 AI 学习管家（AI Learning Manager），践行以下原则：
1. 目标驱动：一切以学习者的目标达成为准绳，不做与目标无关的事；
2. 自主管理：主动规划、主动跟进、主动干预，而不是等待指令；
3. 自适应：基于证据调整路径与节奏，而非机械执行计划；
4. 主动关怀：像一位优秀的私人教师那样观察、诊断、行动；
5. 结果导向：以“能做到”（知行合一）为最终标准，完成不等于掌握；
6. 人机协同：重大变化尊重学习者意愿，需学习者确认后才生效。

铁律：
- 你只能依据提供给你的事实进行分析与建议，绝不允许臆造学习者的学习数据；
- 你的职责边界是“分析、生成、建议”，学习状态的最终判定由系统业务规则完成；
- 对学习者的判断要区分事实与推测：事实标注高置信度，推测标注低置信度。"""

# --------------------------------------------------------------------------
# Knowledge Builder — goal → knowledge system (§5.2)
# --------------------------------------------------------------------------

PROMPT_BUILD_KNOWLEDGE = """学习者的目标是“{goal_title}”。
目标描述：{goal_description}
目标水平：{target_level}
成功标准：{success_criteria}
可用参考材料：
{source_digest}

请为目标构建完整的知识体系：一个知识领域（domain），以及为达成该目标必须掌握的知识点（knowledge_points）。

要求：
- 知识点数量适中（{min_points}-{max_points} 个），覆盖从入门到目标水平的必经路径；
- 每个知识点标注类型（概念/事实/原理/程序/技能/方法）、难度（BEGINNER/INTERMEDIATE/ADVANCED）、建议学习方法（从 学(STUDY)/练(PRACTICE)/用(APPLY)/讲(EXPLAIN)/温(REVIEW) 中选择最匹配的 1-3 种）与预计学习分钟数；
- 通过 prerequisites 字段表达知识点之间的前置依赖（引用知识点的 code），系统会据此建图；
- 领域与知识点的 name 简洁准确（不超过 20 字），description 是一句话的清晰定义；
- 如果参考材料中有价值，优先基于材料内容提炼知识点。"""

SCHEMA_BUILD_KNOWLEDGE = {
    "domain": {"name": "string (≤20字)", "description": "string"},
    "knowledge_points": [
        {
            "code": "string 如 KP-001（必须唯一，格式 KP-序号）",
            "name": "string",
            "description": "string（一句话定义）",
            "knowledge_type": "CONCEPT|FACT|PRINCIPLE|PROCEDURE|SKILL|METHOD",
            "difficulty": "BEGINNER|INTERMEDIATE|ADVANCED",
            "recommended_methods": ["STUDY|PRACTICE|APPLY|EXPLAIN|REVIEW"],
            "tags": ["string"],
            "est_minutes": "int",
            "prerequisites": ["前置知识点的 code，无则空数组"],
        }
    ],
    "rationale": "string（构建思路说明）",
}

# --------------------------------------------------------------------------
# Curriculum Planner — knowledge system → learning path (§5.3)
# --------------------------------------------------------------------------

PROMPT_PLAN_PATH = """请为学习者规划学习路径。

目标：{goal_title}（水平：{target_level}）
学习者画像：{learner_digest}
知识点清单（含前置依赖）：
{points_digest}

要求：
- 拓扑排序所有前置依赖，给出唯一的推荐学习顺序（order 从 1 开始连续编号）；
- 严格前置的知识点用 sequence=FIXED，其余用 sequence=FLEXIBLE；
- 估算每个节点学习时长（est_minutes），并对整条路径给出里程碑式说明；
- 路径必须服务于目标达成，不堆砌不必要的知识点。"""

SCHEMA_PLAN_PATH = {
    "path": {"title": "string", "description": "string"},
    "nodes": [
        {
            "order": "int",
            "knowledge_point_code": "string",
            "sequence": "FIXED|FLEXIBLE",
            "est_minutes": "int",
            "reason": "string（为何放在此处）",
        }
    ],
}

# --------------------------------------------------------------------------
# Course Agent — outline → lessons (§5.4, §8)
# --------------------------------------------------------------------------

PROMPT_COURSE_OUTLINE = """请为以下知识点生成一门课程的大纲。

课程主题：{topic}
知识点（本次课程必须覆盖）：
{points_digest}
学习者画像：{learner_digest}

要求：
- 课程由 3-8 节课（lessons）组成，按学习顺序编号；
- 每节课聚焦 1-2 个知识点，给出明确的学习目标（objectives，学习者学完后能做到什么，用可验证的行为动词）；
- 每节课标注建议的学习方法 method（STUDY/PRACTICE/APPLY/EXPLAIN/REVIEW 之一）与预计分钟数；
- 课程要有清晰的递进逻辑：从感知到理解，从理解到应用。"""

SCHEMA_COURSE_OUTLINE = {
    "title": "string（课程标题）",
    "description": "string（课程一句话介绍）",
    "lessons": [
        {
            "order": "int",
            "title": "string",
            "objectives": ["string（可验证的学习目标）"],
            "knowledge_point_codes": ["string"],
            "method": "STUDY|PRACTICE|APPLY|EXPLAIN|REVIEW",
            "est_minutes": "int",
        }
    ],
}

PROMPT_WRITE_LESSON = """请撰写下面这节课的完整教学内容（Markdown 格式）。

课程：{course_title}
本节课：{lesson_title}
学习目标：{objectives}
涉及知识点：{points_digest}
学习者画像：{learner_digest}
课程记忆（本课程进行中积累的上下文）：
{course_memory_digest}
前后课程标题：{neighbors}

写作要求：
- 用中文撰写，语气亲切自然，像一位优秀教师在面授；
- 结构清晰：以简短的引入开始，正文分节（用二级/三级标题），结尾有本课小结；
- 每个关键概念先用一句话讲清楚（是什么），再讲为什么（原理），最后讲怎么用（示例）；
- 示例必须具体可操作，禁止空泛套话；学习者画像偏好时优先使用其喜欢的风格；
- 尊重学习者已有水平：入门者多铺垫，进阶者直切要点；
- 长度与预计时长匹配（约 {est_minutes} 分钟的阅读量，1 分钟 ≈ 200-300 字）；
- 只输出 Markdown 正文本身，不要输出课程标题。"""

PROMPT_REVISE_LESSON = """下面的课程内容在质量检查中未通过，请修复后重新输出完整内容（Markdown 格式）。

原内容：
{lesson_body}

检查发现的问题：
{findings}

要求：只针对问题修复，保持原有结构与风格；输出修复后的完整 Markdown 正文。"""

# --------------------------------------------------------------------------
# Content Quality Checker (§10.2)
# --------------------------------------------------------------------------

PROMPT_QUALITY_CHECK = """请以严格的内容质量检查员身份审查以下课程内容。

知识点定义（内容必须与之一致）：
{points_digest}

课程内容：
{lesson_body}

从六个维度检查，每个维度都认真核对：
- accuracy（准确性）：是否有事实/概念错误，是否与知识点定义矛盾；
- completeness（完整性）：是否覆盖了该节课的全部学习目标；
- coherence（连贯性）：行文逻辑是否通顺，是否有断裂或前后矛盾；
- formatting（格式）：Markdown 是否规范，标题层级是否正确；
- citation（引用）：示例/数据是否可核实，是否出现臆造的引用；
- safety（安全）：是否包含有害、误导或不当内容。

注意：goal 的内容质量是发布门禁，宁可从严，不可放过。"""

SCHEMA_QUALITY_CHECK = {
    "passed": "bool（无 MEDIUM 以上问题时为 true）",
    "score": "float 0-1",
    "findings": [
        {
            "category": "accuracy|completeness|coherence|formatting|citation|safety",
            "severity": "HIGH|MEDIUM|LOW",
            "description": "string（问题描述，引用原文）",
            "suggestion": "string（修改建议）",
        }
    ],
    "overall_comment": "string",
}

# --------------------------------------------------------------------------
# Exercise Generator (§8 练)
# --------------------------------------------------------------------------

PROMPT_GENERATE_EXERCISES = """请为知识点生成练习题。

知识点：{point_digest}
学习者画像：{learner_digest}
题目要求：{requirement}

要求：
- 每道题必须针对该知识点的核心理解，而非死记硬背；
- 题型在 SINGLE_CHOICE / TRUE_FALSE / SHORT_ANSWER / CODE 中选择（由知识点类型决定）；
- 每道题给出答案与详细解析（explanation 要讲清楚为什么，而不是只给结论）；
- 难度与知识点难度和学习者当前水平匹配。"""

SCHEMA_GENERATE_EXERCISES = {
    "questions": [
        {
            "question_type": "SINGLE_CHOICE|TRUE_FALSE|SHORT_ANSWER|CODE",
            "question": "string",
            "options": ["string（选择题选项，其他题型为空数组）"],
            "answer": "string（选择题为选项内容本身；简答/代码为参考答案）",
            "explanation": "string（解析）",
            "difficulty": "BEGINNER|INTERMEDIATE|ADVANCED",
        }
    ]
}

# --------------------------------------------------------------------------
# Assessment Engine — 讲 (explain) evaluation (§8 讲, §9)
# --------------------------------------------------------------------------

PROMPT_ASSESS_EXPLANATION = """请评估学习者对知识点的讲解（“费曼式”检验：能讲清楚才是真的懂）。

知识点：{point_digest}
学习者的讲解：
{explanation}

要求：
- 判断学习者是否真正掌握（而不是背诵）：概念是否准确、逻辑是否自洽、能否举出正确例子、是否点出常见误区；
- score 为 0-1 的掌握程度评分；confidence 为你对该评分的置信度（讲解内容太短或太模糊时应降低置信度）；
- mastery_state：讲解准确完整给 MASTERED；有明显概念错误给 REVIEW_REQUIRED；介于之间给 IN_PROGRESS；
- feedback 用中文、具体、可操作（指出对在哪里、错在哪里、下一步学什么）；
- 绝不臆造：讲解中没有提到的内容不要当作学习者已掌握。"""

SCHEMA_ASSESS_EXPLANATION = {
    "score": "float 0-1",
    "confidence": "float 0-1",
    "mastery_state": "MASTERED|REVIEW_REQUIRED|IN_PROGRESS",
    "strengths": ["string"],
    "gaps": ["string（未讲清或讲错的部分）"],
    "feedback": "string",
}

# --------------------------------------------------------------------------
# Learning Manager — diagnose & decide (§7)
# --------------------------------------------------------------------------

PROMPT_DIAGNOSE = """请基于以下真实数据诊断学习者当前的问题。

目标：{goal_digest}
学习者画像：{learner_digest}
近期学习任务状态：
{tasks_digest}
知识点掌握情况：
{mastery_digest}
近期学习事件：
{events_digest}

十类问题及典型信号（按此分类诊断）：
1. GOAL_DRIFT（目标漂移）：行为与目标明显不一致；
2. PROGRESS_BEHIND（进度落后）：按截止日期推算进度明显落后于计划；
3. STALLED（停滞拖延）：多日无学习行为，任务持续过期未完成；
4. COMPREHENSION_DIFFICULTY（理解困难）：同一知识点反复学习/测试分数持续偏低/任务反复卡住；
5. EXERCISE_WEAKNESS（练习薄弱）：练习正确率明显偏低；
6. MASTERY_DECAY（掌握衰减/复习逾期）：复习任务逾期未做，已掌握内容长期未温习；
7. METHOD_MISMATCH（方法不当）：任务完成但掌握度低，学习方法与知识点类型不匹配；
8. MOTIVATION_DROP（动力下降）：学习频率/时长明显下滑，跳过任务比例上升；
9. TIME_CONFLICT（时间冲突）：实际耗时持续远超每日时间预算；
10. CONTENT_ISSUE（内容问题）：问题源于课程内容质量缺陷而非学习者。

诊断规则：
- 每个问题必须引用具体证据（evidence 中引用真实数据），无证据不诊断；
- priority 按影响分三级：HIGH（威胁目标达成/理解受阻）、MEDIUM（进度/掌握受损）、LOW（轻微偏差）；
- 学习者状态正常时返回空 problems 数组，不要为了干预而干预；
- 宁可漏诊不可误诊：证据不足时不要给出 HIGH 优先级。"""

SCHEMA_DIAGNOSE = {
    "problems": [
        {
            "type": "GOAL_DRIFT|PROGRESS_BEHIND|STALLED|COMPREHENSION_DIFFICULTY|"
            "EXERCISE_WEAKNESS|MASTERY_DECAY|METHOD_MISMATCH|MOTIVATION_DROP|"
            "TIME_CONFLICT|CONTENT_ISSUE",
            "priority": "HIGH|MEDIUM|LOW",
            "evidence": ["string（引用真实数据）"],
            "narrative": "string（一句话诊断）",
        }
    ]
}

PROMPT_DECIDE = """你是学习者的 AI 学习管家。基于以下诊断出的问题，决定本轮要采取的干预措施。

诊断结果：
{problems_digest}
目标与计划上下文：
{goal_digest}
可用干预措施（action 类型固定为以下几种）：
- SCHEDULE_REVIEW：为指定知识点安排复习（target 为 knowledge_point_id）；
- ADD_PRACTICE：为薄弱知识点生成针对性练习（target 为 knowledge_point_id）；
- SIMPLIFY_CONTENT：为难以理解的知识点生成一篇降维讲解（target 为 knowledge_point_id）；
- ENCOURAGE：发送一条主动关怀/鼓励消息（不催促，先共情再建议）；
- REMIND：温和提醒（临近截止/任务堆积/复习到期）；
- ADJUST_PLAN：提出调整路径的方案（生成 proposal，由学习者确认后才生效）；
- NONE：本轮不干预。

决策规则：
- 优先级决定成本：HIGH 问题才允许 ADJUST_PLAN / SIMPLIFY_CONTENT 等高成本动作；LOW 问题优先用消息类轻量动作；
- 一次最多 {max_actions} 个动作，聚焦最重要的问题，不要动作轰炸；
- 同一问题短期内已有干预记录时不要重复（我会提供近期干预历史：{recent_interventions}）；
- REMIND/ENCOURAGE 的 message 用中文撰写，具体、简短（≤80字）、有温度，引用真实数据（如“你已经 3 天没学啦”），禁止说教；
- NEEDS_CONFIRMATION：ADJUST_PLAN 一律生成待确认方案，绝不直接执行。"""

SCHEMA_DECIDE = {
    "actions": [
        {
            "action": "SCHEDULE_REVIEW|ADD_PRACTICE|SIMPLIFY_CONTENT|ENCOURAGE|REMIND|ADJUST_PLAN|NONE",
            "priority": "HIGH|MEDIUM|LOW",
            "problem_type": "对应诊断出的问题类型",
            "target_type": "KNOWLEDGE_POINT|GOAL|TASK|NONE",
            "target_id": "string（无则为空字符串）",
            "message": "string（消息类动作必填，其他为空）",
            "payload": "object（如调整方案的具体内容）",
            "reason": "string（决策依据）",
        }
    ]
}

PROMPT_EVALUATE_CYCLE = """请评估本轮干预的执行结果，输出简短的循环小结。

诊断：{problems_digest}
决策并执行的动作及结果：{results_digest}

要求：summary 为 2-3 句中文小结（本轮发现了什么、做了什么、效果预期）；
interventions_had_effect 为 true/false（本轮动作是否可能已产生实际影响）；
需要持续关注的问题写入 watch_types（下一轮重点观察的问题类型）。"""

SCHEMA_EVALUATE_CYCLE = {
    "summary": "string",
    "interventions_had_effect": "bool",
    "watch_types": ["string（问题类型）"],
}

# --------------------------------------------------------------------------
# Memory Manager — event stream → three-layer memory (§12)
# --------------------------------------------------------------------------

PROMPT_MEMORY_INFERENCE = """请从学习者的学习事件中提炼值得长期记住的信息。

学习者画像（已知）：{known_memories}
近期事件：
{events_digest}

提炼规则（铁律）：
- 只输出值得跨会话保留的信息（稳定的偏好/风格/目标语境/行为规律），一次性事实不要提炼；
- 每条记忆必须如实标注 source：
  * USER_INPUT：学习者明确陈述过的（原话可见于事件）；
  * SYSTEM_FACT：系统确定性数据反映的事实（如考试成绩）；
  * AI_ASSESSMENT：基于多条证据可下的评估；
  * AI_GUESS：单条证据的推测（置信度必须低）；
- confidence 与 source 匹配：USER_INPUT=0.9+，SYSTEM_FACT=0.9+，AI_ASSESSMENT=0.6-0.8，AI_GUESS≤0.4；
- memory_type 在 PREFERENCE/LEARNING_STYLE/GOAL_CONTEXT/BEHAVIOR/KNOWLEDGE_STATE 中选择；
- 与学习者画像重复的信息不要输出；
- 没有值得记住的就返回空数组，不要硬凑。"""

SCHEMA_MEMORY_INFERENCE = {
    "memories": [
        {
            "memory_type": "PREFERENCE|LEARNING_STYLE|GOAL_CONTEXT|BEHAVIOR|KNOWLEDGE_STATE",
            "key": "string（稳定的短键名，如 prefers_short_sessions）",
            "value": "object",
            "source": "USER_INPUT|SYSTEM_FACT|AI_ASSESSMENT|AI_GUESS",
            "confidence": "float 0-1",
            "rationale": "string（依据哪条事件）",
        }
    ]
}

# --------------------------------------------------------------------------
# Assessment Engine — subjective answer grading (练, §8)
# --------------------------------------------------------------------------

PROMPT_GRADE_SUBJECTIVE = """请严格评分学习者的主观题作答。

题目：{question}
参考答案：{expected_answer}
学习者的作答：
{user_answer}

评分要求：
- score 为 0-1 的正确性评分：关键点覆盖程度 + 概念准确性，不考虑文采；
- confidence 为你对该评分的置信度：作答太短、太模糊或参考答案不足以判定时降低置信度；
- feedback 用中文、简短、可操作：指出对/错在哪里，下一步学什么；
- 宁可保守：不确定的判断给低 confidence，绝不臆造学习者未提及的内容。"""

SCHEMA_GRADE_SUBJECTIVE = {
    "score": "float 0-1",
    "confidence": "float 0-1",
    "feedback": "string",
    "missed_points": ["string（未覆盖的关键点）"],
}

__all__ = [name for name in globals() if name.startswith(("PROMPT_", "SCHEMA_", "PRINCIPLES"))]
