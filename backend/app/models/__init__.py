"""Domain model package (whitepaper §12).

Re-exports every entity plus ``Base`` so ``app.core.database.init_db`` can
``import app.models`` and call ``Base.metadata.create_all`` for the full
schema in tests/dev, and so Alembic autogenerate sees every table.
"""

from app.models.agent import (
    AgentCheckpoint,
    AgentDefinition,
    AgentRun,
    AgentRunStatus,
    AgentType,
)
from app.models.assessment import (
    Assessment,
    AssessmentType,
    MasteryRecord,
    MasteryState,
    ReviewStatus,
    ReviewTask,
    ReviewType,
)
from app.models.base import Base, TimestampMixin, UUIDPKMixin, pg_enum
from app.models.content import (
    ContentQualityReport,
    ContentSource,
    QualityStage,
    QualityStatus,
    Reviewer,
    SourceStatus,
    SourceType,
)
from app.models.curriculum import (
    ContentFormat,
    Course,
    CourseStatus,
    CourseVersion,
    LearningPath,
    LearningPathNode,
    Lesson,
    PathStatus,
    Sequence,
)
from app.models.goal import GoalStatus, LearningGoal
from app.models.identity import LearnerProfile, User, UserSession
from app.models.knowledge import (
    Difficulty,
    KnowledgeDomain,
    KnowledgePoint,
    KnowledgeRelation,
    KnowledgeType,
    RelationType,
)
from app.models.memory import CourseMemory, EventSource, LearnerMemory, LearningEvent, MemoryType
from app.models.practice import (
    Exercise,
    ExerciseAttempt,
    LearningTask,
    PracticeProject,
    QuestionType,
    TaskStatus,
    TaskType,
)

__all__ = [
    # base
    "Base",
    "TimestampMixin",
    "UUIDPKMixin",
    "pg_enum",
    # identity
    "User",
    "LearnerProfile",
    "UserSession",
    # goal
    "GoalStatus",
    "LearningGoal",
    # knowledge
    "KnowledgeType",
    "Difficulty",
    "RelationType",
    "KnowledgeDomain",
    "KnowledgePoint",
    "KnowledgeRelation",
    # curriculum
    "PathStatus",
    "Sequence",
    "CourseStatus",
    "ContentFormat",
    "LearningPath",
    "LearningPathNode",
    "Course",
    "CourseVersion",
    "Lesson",
    # practice
    "TaskType",
    "TaskStatus",
    "QuestionType",
    "LearningTask",
    "Exercise",
    "ExerciseAttempt",
    "PracticeProject",
    # assessment
    "AssessmentType",
    "MasteryState",
    "ReviewType",
    "ReviewStatus",
    "Assessment",
    "MasteryRecord",
    "ReviewTask",
    # memory
    "EventSource",
    "MemoryType",
    "LearningEvent",
    "LearnerMemory",
    "CourseMemory",
    # agent
    "AgentType",
    "AgentRunStatus",
    "AgentDefinition",
    "AgentRun",
    "AgentCheckpoint",
    # content
    "SourceType",
    "SourceStatus",
    "QualityStage",
    "QualityStatus",
    "Reviewer",
    "ContentSource",
    "ContentQualityReport",
]
