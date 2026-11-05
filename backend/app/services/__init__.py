"""Service layer (whitepaper §13.2) — the deterministic business core.

Services own rules, state transitions, permissions and transactions. AI agents
(and only AI agents' proposals) enter the system through these functions; the
services decide what actually gets written. Every mutation that the AI Learning
Manager might reason over also records a LearningEvent so the Observe step of
the intervention loop (§7) is always grounded in real data.
"""
