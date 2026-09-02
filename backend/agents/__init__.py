"""
Agentic evidence layer (Spec §20, §23; mentor architecture review 01-09-2026).

Four agents that widen what this system can SHOW. They do not widen what it is
willing to ASSERT.

  Agent 1  ingestion    - clinician-uploaded documents into the vector store
  Agent 2  filtration   - the judge over web results, backend/agents/filtration.py
  Agent 3  grounding    - precedence-aware fusion, backend/agents/grounding.py
  Agent 4  compose      - structured, cited response

THE BOUNDARY THIS PACKAGE MUST NOT CROSS: backend.rules.engine does not import
anything here, in the same way and for the same reason it does not import
backend.rag. Every deterministic safety warning fires with this entire package
absent, the network down and no API key configured. An agent can add evidence to
an answer. An agent can never cause a warning to fire, and - the failure that
would actually harm someone - can never cause one to stay silent.
"""
