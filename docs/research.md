# Chat And Deep Research

intextum supports two related but different conversation modes:

- Chat: interactive answers over accessible document context.
- Deep research: asynchronous report generation with planning, evidence
  retrieval, section drafting, verification, and persisted report output.

Both modes use the same user/session/ACL foundation and the same configured chat
model settings, but they have different execution paths.

## Chat Mode

Chat mode is optimized for interactive response streaming.

High-level flow:

1. The frontend submits a conversation run in chat mode.
2. Backend validates the session and request payload.
3. Backend prepares a request-scoped chat graph.
4. The chat graph retrieves relevant document context through tools as needed.
5. The configured chat model streams a response.
6. Backend persists replayable run events and visible conversation messages.

The chat graph combines base system prompt, file enrichment context, and any
relevant previous research-report context into one leading system message before
calling the model. This keeps compatibility with OpenAI-compatible providers
that reject system messages after the first message.

## Deep Research Mode

Deep research is a background run that produces a persisted research report. It
does not stream token-by-token prose like normal chat; it emits progress events
for graph phases and stores the completed report.

The research graph is built in the `api/research/graph/` package.

Phases:

1. `collect_structured_facts`
2. `plan_research`
3. `retrieve_evidence`
4. `draft_report`
5. `verify_report`

### Structured Facts

The graph first loads effective content-enrichment facts for the request scope.
These include reviewed classification/extraction data when available.

Structured facts are used as orientation for planning and section drafting.
They are not cited directly. Report claims should cite retrieved section
evidence.

### Planning

The planner asks the model for JSON containing:

- report title
- research questions
- outline sections

The plan is constrained to a small number of questions and sections so retrieval
and drafting stay bounded.

### Evidence Retrieval

For each planned section, the graph generates query candidates from:

- original prompt
- section heading
- section question

It embeds those queries, runs ACL-scoped semantic search, parses retrieved
chunks, and ranks section candidates. Reviewed enrichment evidence can also
contribute candidates when relevant.

When deep research is scoped to exactly one selected document, the graph also
loads that document through the same ACL-scoped chunk path used by the chat
`get_document` tool. The assembled document text is clipped by
`CHAT_DOCUMENT_MAX_CHARS`, registered as the first citation source, and included
as section evidence for every planned section. Semantic chunk retrieval still
runs afterward so the report can combine whole-document recall with focused
chunk-level evidence.

Evidence is deduplicated and assigned citation indices. Each section receives a
bounded evidence set.

### Drafting

Each section is drafted separately. The section prompt includes:

- original user prompt
- report title
- section heading/question
- relevant structured facts
- section evidence with citation ids

The model must return JSON with a `body` field. Section bodies should use inline
citations like `[1]` and cite only the section evidence.

### Verification

The graph verifies the report after drafting:

- selects referenced images from cited sources
- checks for invalid citations
- checks for sections with evidence but no citations
- checks for cross-section citation misuse
- composes final markdown with a source list

Verification issues are stored with the report and surfaced by the frontend.

## Persistence And Events

Research runs are executed by the chat runner infrastructure. A run has:

- run id
- conversation id
- mode
- claim/heartbeat state
- replayable events
- optional research report id

When a research run completes:

1. `ResearchReportService` stores title, outline, sections, sources, images,
   verification issues, and final markdown.
2. Backend appends an assistant message to the conversation containing the
   report markdown.
3. The message metadata marks it as a research report and includes report
   details.
4. A completion event is published for user notifications.

## Follow-Up Chat On Research Reports

Follow-up chat can use prior research reports as context. The helper in
`api/chat/graph/report_context.py` finds the latest report message, selects
relevant sections for the follow-up question, and primes the source collector
with report-backed sources.

This lets follow-up chat cite the original report sources instead of treating
the generated report as ungrounded text.

## Citations And Sources

Research citations are numeric markers such as `[1]`. A source payload includes
file path, display name, optional content item id, page numbers, document refs,
quote, images, and citation index.

The report source list is generated from the same source payloads used during
drafting and verification.

## Scope And ACLs

Research retrieval is user- and ACL-scoped:

- `build_user_trustees(runtime.user)` limits vector search to content the user
  may access.
- Optional `context_file_paths` further constrain the scope.
- Structured facts are loaded through the same context scope.

Deep research should never bypass the content ACL layer.

## Failure Modes

Common research failures:

- Model returns invalid JSON for planning or section drafting.
- Retrieved evidence is too sparse for a section.
- Model cites invalid or cross-section citation ids.
- Embedding/search provider failure.
- Run cancellation or runner heartbeat loss.

Invalid structured model responses are surfaced as runtime errors. Verification
issues are stored when the report completes but has citation problems.

## When To Use Chat vs Research

Use chat when:

- the user needs a quick answer
- iterative back-and-forth matters
- the answer can be short and direct

Use deep research when:

- the user needs a report-like output
- multiple sources need to be compared
- citations and section structure matter
- generation can run asynchronously

Deep research is not a replacement for content enrichment. Enrichment extracts
stable document facts; research uses those facts and document chunks to produce
grounded narrative analysis.
