# Enterprise AI Employee architecture

The backend follows a layered, dependency-directed structure. HTTP concerns live in `app/api`; application orchestration belongs in `app/services`; persistence concerns remain in `app/database` and `app/models`; transport contracts live in `app/schemas`. The LangGraph single-agent runtime lives in `app/agents`; the controlled action boundary lives in `app/tools`.

Pydantic Settings parses environment configuration once. Readiness verifies PostgreSQL and Redis, preventing the service from reporting ready when required infrastructure is unavailable.

## Tool execution boundary

`ToolRegistry` contains only explicitly registered `BaseTool` implementations. `ToolExecutor` resolves a registry entry, validates Pydantic input, checks the trusted `ToolContext` role, executes the tool, validates its output, and returns a structured `ToolResult`. Unexpected tool exceptions are converted to safe errors rather than escaping through the agent runtime.

The agent derives `ToolContext.user_id` and role from the authenticated API user, not request data. Tool results are stored as `tool` messages using the existing message metadata field. The calculator uses a restricted Python AST evaluator; it never uses `eval` or `exec`. No shell, filesystem, browser, arbitrary Python, or unrestricted network tools are registered.

## Knowledge base and RAG

The knowledge subsystem is layered under `app/services/knowledge.py`: `DocumentExtractor` handles TXT, Markdown, and text-based PDFs; `TextChunker` produces deterministic bounded chunks; `EmbeddingService` uses local Ollama embeddings; and `KnowledgeRepository` persists documents and embeddings in PostgreSQL. Files are written beneath the configured document-storage root using UUID-based filenames, never a client-provided path.

`KnowledgeService.search` filters every chunk query by the authenticated user before applying cosine similarity scoring. The existing LangGraph state carries `retrieved_context` and source metadata independently from conversation memory. The LLM prompt instructs it to use document evidence only and identify when available documents are insufficient. Tool execution remains separate, although a retrieved budget can safely feed the existing restricted calculator for percentage calculations.
