"""Agent runtime package (whitepaper §12, §13.2 module "Agent Runtime").

The AI side of DoKnow. Agents *analyze, generate and propose* — they never
write business state directly; all mutations go through the service layer
(app/services), which owns rules, permissions and transactions.

Contents:
- ``llm``      — the only door to model capabilities (provider-agnostic)
- ``runtime``  — AgentRun lifecycle: execute, heartbeat, retry, checkpoint
- graphs       — LangGraph workflows (AI Learning Manager, Course Agent, ...)
"""
