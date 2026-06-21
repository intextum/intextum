import { useState } from "react";
import {
  cloneDocumentClassDraft,
  createEmptyDocumentClassDraft,
  type DocumentClassDraft,
  type DocumentExtractionSchemaDraft,
  toDocumentClassDrafts,
} from "@/lib/content-enrichment-admin";

export function useContentEnrichmentDrafts() {
  const [documentClassesDraft, setDocumentClassesDraft] = useState<DocumentClassDraft[]>([]);

  const applyCatalogDrafts = (catalog: { document_classes?: unknown }) => {
    setDocumentClassesDraft(toDocumentClassDrafts(catalog.document_classes));
  };

  const updateDocumentClassDraft = (index: number, patch: Partial<DocumentClassDraft>) => {
    setDocumentClassesDraft((current) =>
      current.map((entry, entryIndex) => (entryIndex === index ? { ...entry, ...patch } : entry)),
    );
  };

  const addDocumentClassDraft = (initial?: DocumentClassDraft) => {
    setDocumentClassesDraft((current) => [
      ...current,
      initial ? cloneDocumentClassDraft(initial) : createEmptyDocumentClassDraft(),
    ]);
  };

  const removeDocumentClassDraft = (index: number) => {
    setDocumentClassesDraft((current) => current.filter((_, entryIndex) => entryIndex !== index));
  };

  const updateDocumentClassExtractionSchema = (
    classIndex: number,
    extractionSchema: DocumentExtractionSchemaDraft | null,
  ) => {
    updateDocumentClassDraft(classIndex, { extraction_schema: extractionSchema });
  };

  return {
    documentClassesDraft,
    applyCatalogDrafts,
    updateDocumentClassDraft,
    addDocumentClassDraft,
    removeDocumentClassDraft,
    updateDocumentClassExtractionSchema,
  };
}
