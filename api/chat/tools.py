"""LangChain tools used by the chat graph."""

from langchain_core.tools import tool

from chat.runtime import ChatRuntime
from chat.toolbox import ChatToolbox


def build_chat_tools(runtime: ChatRuntime):
    """Build request-scoped tools for the chat graph."""
    toolbox = ChatToolbox(runtime)

    @tool
    async def search_documents(query: str) -> str:
        """Search indexed documents for passages relevant to the user's question."""
        return await toolbox.search_documents(query)

    @tool
    async def get_document(file_path: str) -> str:
        """Retrieve the full text of a specific accessible document."""
        return await toolbox.get_document(file_path)

    return [search_documents, get_document]
