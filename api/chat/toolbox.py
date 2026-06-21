"""Request-scoped orchestration for chat LangChain tools."""

import logging

from chat.context import resolve_get_document_target_path
from chat.documents import (
    assemble_document_text,
    build_document_source,
    resolve_document_path,
    truncate_document_text,
)
from chat.retrieval import RetrievedChunk, parse_retrieved_chunks
from chat.runtime import ChatRuntime
from services.ai_limits import create_embedding_response
from services.utils import compute_content_item_id
from services.vector import VectorService

logger = logging.getLogger(__name__)

NO_CONTEXT_FILES_MESSAGE = "No context files selected. Ask the user to add files first."
NO_RELEVANT_DOCUMENTS_MESSAGE = "No relevant documents found."
DOCUMENT_OUTSIDE_CONTEXT_MESSAGE = (
    "Document is outside the selected context. Ask the user to add it to context first."
)
DOCUMENT_FETCH_LIMIT = 200


class ChatToolbox:
    """Owns request-scoped search/document tool behavior for one chat run."""

    def __init__(self, runtime: ChatRuntime):
        self.runtime = runtime

    @property
    def context_scope(self):
        """Return the cached context scope for this tool run."""
        return self.runtime.context_scope

    def _log_context(self, tool_name: str) -> None:
        """Log the current request context size for one tool invocation."""
        logger.info(
            "%s context: context_files=%d resolved_files=%d",
            tool_name,
            len(self.context_scope.raw_paths),
            len(self.context_scope.constraints),
        )

    def _selection_error(self) -> str | None:
        """Return the common message for unresolved selected-file context."""
        if self.context_scope.has_selection and not self.context_scope.has_constraints:
            return NO_CONTEXT_FILES_MESSAGE
        return None

    @staticmethod
    def _page_label(page_numbers: list[int]) -> str:
        """Format a compact page label for search result snippets."""
        if not page_numbers:
            return ""
        return f" (p. {', '.join(str(page) for page in page_numbers)})"

    @staticmethod
    def _document_not_found_message(target_path: str) -> str:
        """Build the user-facing missing-document message."""
        return f"Document not found or not accessible: {target_path}"

    async def _semantic_search(self, query: str) -> list[RetrievedChunk]:
        """Embed the query and run the vector search for search_documents."""
        response = await create_embedding_response(
            self.runtime.embed_client,
            self.runtime.settings,
            model=self.runtime.settings.EMBEDDING_MODEL,
            texts=[query],
        )
        query_vector = response.data[0].embedding
        results = await VectorService.semantic_search(
            db=self.runtime.db,
            query_vector=query_vector,
            limit=self.runtime.settings.CHAT_SEARCH_LIMIT,
            file_ids=self.context_scope.file_ids or None,
        )
        return parse_retrieved_chunks(results)

    def _render_search_results(self, chunks: list[RetrievedChunk]) -> str:
        """Convert search results into the numbered tool context shown to the model."""
        if not chunks:
            return NO_RELEVANT_DOCUMENTS_MESSAGE

        folder_name_map = self.context_scope.folder_uuid_to_name
        source_collector = self.runtime.source_collector
        context_parts: list[str] = []
        for chunk in chunks:
            file_path = chunk.resolved_file_path(folder_name_map)
            citation_index = source_collector.add_search_source(
                file_path=file_path,
                content_item_id=chunk.content_item_id or None,
                display_name=chunk.display_name or None,
                content_kind=chunk.content_kind,
                email_from_address=chunk.email_from_address,
                email_sent_at=chunk.email_sent_at,
                parent_display_name=chunk.parent_display_name,
                page_numbers=chunk.page_numbers,
                doc_refs=chunk.doc_refs,
                text=chunk.text,
                image_urls=chunk.image_urls(),
            )
            filename = file_path.split("/")[-1]
            context_parts.append(
                f"[{citation_index}] Document: {filename}"
                f"{self._page_label(chunk.page_numbers)}\n"
                f"Path: {file_path}\n"
                f"{chunk.text}"
            )

        return "\n\n---\n\n".join(context_parts)

    async def search_documents(self, query: str) -> str:
        """Search indexed documents for passages relevant to the user's question."""
        self._log_context("search_documents")
        selection_error = self._selection_error()
        if selection_error is not None:
            return selection_error

        try:
            chunks = await self._semantic_search(query)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Search tool error: %s", exc)
            return "Error searching documents."

        return self._render_search_results(chunks)

    def _resolve_document_target(
        self, raw_file_path: str
    ) -> tuple[str | None, str | None]:
        """Resolve one get_document input into a canonical API path."""
        return resolve_get_document_target_path(
            raw_file_path=raw_file_path,
            context_scope=self.context_scope,
            source_paths=self.runtime.source_collector.source_paths(),
        )

    async def _fetch_document_chunks(
        self, content_item_id: str
    ) -> list[RetrievedChunk]:
        """Load and normalize document chunks for get_document."""
        results = await VectorService.fetch_document_chunks(
            db=self.runtime.db,
            content_item_id=content_item_id,
            limit=DOCUMENT_FETCH_LIMIT,
        )
        return parse_retrieved_chunks(results)

    async def get_document(self, file_path: str) -> str:
        """Retrieve the full text of a specific accessible document."""
        self._log_context("get_document")
        selection_error = self._selection_error()
        if selection_error is not None:
            return selection_error

        resolved_target_path, resolution_error = self._resolve_document_target(
            file_path
        )
        if resolution_error:
            return resolution_error

        target_path = resolved_target_path or file_path
        try:
            folder_uuid, relative_path = resolve_document_path(
                target_path,
                self.context_scope.folder_name_to_uuid,
            )
        except ValueError as exc:
            return str(exc)

        if self.context_scope.has_selection and not self.context_scope.contains(
            folder_uuid, relative_path
        ):
            logger.warning("get_document blocked by selected-files scope")
            return DOCUMENT_OUTSIDE_CONTEXT_MESSAGE

        content_item_id = compute_content_item_id(folder_uuid, relative_path)
        try:
            document_chunks = await self._fetch_document_chunks(content_item_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("get_document error: %s", exc)
            return f"Error retrieving document: {target_path}"

        if not document_chunks:
            return self._document_not_found_message(target_path)

        full_text = assemble_document_text(document_chunks)
        full_text = truncate_document_text(
            full_text,
            self.runtime.settings.CHAT_DOCUMENT_MAX_CHARS,
        )
        self.runtime.source_collector.add_source(
            build_document_source(
                target_path,
                document_chunks,
                full_text,
                content_item_id=content_item_id,
                display_name=document_chunks[0].display_name
                if document_chunks
                else None,
            )
        )

        filename = target_path.split("/")[-1]
        return f"# Full document: {filename}\n\n{full_text}"
