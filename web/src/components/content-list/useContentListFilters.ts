import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AllFilesBatchFilters,
  ContentEnrichmentReviewStatus,
  ContentItemKind,
} from "@/dataProvider";
import {
  serializeFieldFilters,
  parseFieldFilters,
  topLevelField,
  type FieldFilterDtype,
  type FieldFilterPredicate,
} from "@/lib/field-filters";

import type { SortBy, SortOrder } from "./types";

export type ContentListFilterKind =
  | "name"
  | "content_kind"
  | "document_class"
  | "extraction_schema"
  | "extension"
  | "status"
  | "review_status"
  | "stale_enrichment";

export interface ContentListFilterChip {
  kind: ContentListFilterKind;
  value: string;
  remove: () => void;
}

interface UseAllFilesFiltersOptions {
  /** Folder-prefixed path; scopes filtered results to the current folder subtree. */
  currentPath?: string;
  initialSortBy: SortBy;
  initialSortOrder: SortOrder;
  initialContentKindFilter?: ContentItemKind | "";
  initialDocumentClassFilter: string;
  initialExtractionSchemaFilter: string;
  initialExtractionFieldFilter: string;
  /** Raw JSON string of field predicates from the URL (stable identity). */
  initialFieldFilters: string;
  initialStaleOnly: boolean;
  initialStatusFilter: string;
  initialReviewStatusFilter: ContentEnrichmentReviewStatus | "";
  onActiveFiltersChange?: (filters: AllFilesBatchFilters) => void;
  onDocumentClassFilterChange?: (documentClass: string) => void;
  onExtractionSchemaFilterChange?: (schema: string) => void;
  onExtractionFieldFilterChange?: (field: string) => void;
  onFieldFiltersChange?: (serialized: string) => void;
  onStaleOnlyChange?: (staleOnly: boolean) => void;
  onStatusFilterChange?: (status: string) => void;
  onReviewStatusFilterChange?: (status: ContentEnrichmentReviewStatus | "") => void;
}

export function useContentListFilters({
  currentPath = "",
  initialSortBy,
  initialSortOrder,
  initialContentKindFilter = "",
  initialDocumentClassFilter,
  initialExtractionSchemaFilter,
  initialExtractionFieldFilter,
  initialFieldFilters,
  initialStaleOnly,
  initialStatusFilter,
  initialReviewStatusFilter,
  onActiveFiltersChange,
  onDocumentClassFilterChange,
  onExtractionSchemaFilterChange,
  onExtractionFieldFilterChange,
  onFieldFiltersChange,
  onStaleOnlyChange,
  onStatusFilterChange,
  onReviewStatusFilterChange,
}: UseAllFilesFiltersOptions) {
  const [nameFilter, setNameFilter] = useState("");
  const [debouncedName, setDebouncedName] = useState("");
  const [nameRegex, setNameRegex] = useState(false);
  const [searchPath, setSearchPath] = useState(false);
  const [contentKindFilter, setContentKindFilter] = useState<ContentItemKind | "">(
    initialContentKindFilter,
  );
  const [documentClassFilter, setDocumentClassFilter] = useState(initialDocumentClassFilter);
  const [debouncedDocumentClass, setDebouncedDocumentClass] = useState(initialDocumentClassFilter);
  const [extractionSchemaFilter, setExtractionSchemaFilter] = useState(
    initialExtractionSchemaFilter,
  );
  const [debouncedExtractionSchema, setDebouncedExtractionSchema] = useState(
    initialExtractionSchemaFilter,
  );
  // Focus field: drives value-facet suggestions and schema-field coverage; it
  // does not narrow the result set on its own (predicates do that).
  const [extractionFieldFilter, setExtractionFieldFilter] = useState(initialExtractionFieldFilter);
  const [debouncedExtractionField, setDebouncedExtractionField] = useState(
    initialExtractionFieldFilter,
  );
  const initialPredicates = useMemo(
    () => parseFieldFilters(initialFieldFilters),
    [initialFieldFilters],
  );
  const [fieldPredicates, setFieldPredicates] = useState<FieldFilterPredicate[]>(initialPredicates);
  const [debouncedFieldPredicates, setDebouncedFieldPredicates] =
    useState<FieldFilterPredicate[]>(initialPredicates);
  const [extensionFilter, setExtensionFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter);
  const [staleOnly, setStaleOnly] = useState(initialStaleOnly);
  const [reviewStatusFilter, setReviewStatusFilter] = useState<ContentEnrichmentReviewStatus | "">(
    initialReviewStatusFilter,
  );
  const [sortBy, setSortBy] = useState<SortBy>(initialSortBy);
  const [sortOrder, setSortOrder] = useState<SortOrder>(initialSortOrder);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedName(nameFilter), 300);
    return () => clearTimeout(timer);
  }, [nameFilter]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedDocumentClass(documentClassFilter), 300);
    return () => clearTimeout(timer);
  }, [documentClassFilter]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedExtractionSchema(extractionSchemaFilter), 300);
    return () => clearTimeout(timer);
  }, [extractionSchemaFilter]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedExtractionField(extractionFieldFilter), 300);
    return () => clearTimeout(timer);
  }, [extractionFieldFilter]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedFieldPredicates(fieldPredicates), 300);
    return () => clearTimeout(timer);
  }, [fieldPredicates]);

  useEffect(() => {
    setStaleOnly(initialStaleOnly);
  }, [initialStaleOnly]);

  useEffect(() => {
    setStatusFilter(initialStatusFilter);
  }, [initialStatusFilter]);

  useEffect(() => {
    setContentKindFilter(initialContentKindFilter);
  }, [initialContentKindFilter]);

  useEffect(() => {
    setDocumentClassFilter(initialDocumentClassFilter);
    setDebouncedDocumentClass(initialDocumentClassFilter);
  }, [initialDocumentClassFilter]);

  useEffect(() => {
    setExtractionSchemaFilter(initialExtractionSchemaFilter);
    setDebouncedExtractionSchema(initialExtractionSchemaFilter);
  }, [initialExtractionSchemaFilter]);

  useEffect(() => {
    setExtractionFieldFilter(initialExtractionFieldFilter);
    setDebouncedExtractionField(initialExtractionFieldFilter);
  }, [initialExtractionFieldFilter]);

  useEffect(() => {
    setFieldPredicates(initialPredicates);
    setDebouncedFieldPredicates(initialPredicates);
  }, [initialPredicates]);

  useEffect(() => {
    setReviewStatusFilter(initialReviewStatusFilter);
  }, [initialReviewStatusFilter]);

  useEffect(() => {
    setSortBy(initialSortBy);
  }, [initialSortBy]);

  useEffect(() => {
    setSortOrder(initialSortOrder);
  }, [initialSortOrder]);

  const serializedFieldFilters = useMemo(
    () => serializeFieldFilters(debouncedFieldPredicates),
    [debouncedFieldPredicates],
  );

  const fetchParams = useMemo(
    () => ({
      sort_by: sortBy,
      sort_order: sortOrder,
      name: debouncedName || undefined,
      name_regex: debouncedName ? nameRegex || undefined : undefined,
      search_path: debouncedName ? searchPath || undefined : undefined,
      path: currentPath || undefined,
      content_kind: contentKindFilter || undefined,
      document_class: debouncedDocumentClass || undefined,
      extraction_schema: debouncedExtractionSchema || undefined,
      extraction_field: debouncedExtractionField || undefined,
      field_filters: serializedFieldFilters,
      extension: extensionFilter || undefined,
      status: statusFilter || undefined,
      review_status: reviewStatusFilter || undefined,
      stale_enrichment: staleOnly || undefined,
    }),
    [
      contentKindFilter,
      currentPath,
      debouncedDocumentClass,
      debouncedExtractionField,
      debouncedExtractionSchema,
      debouncedName,
      extensionFilter,
      nameRegex,
      reviewStatusFilter,
      serializedFieldFilters,
      sortBy,
      sortOrder,
      searchPath,
      staleOnly,
      statusFilter,
    ],
  );

  const currentBatchFilters = useMemo<AllFilesBatchFilters>(
    () => ({
      name: debouncedName || undefined,
      name_regex: debouncedName ? nameRegex || undefined : undefined,
      search_path: debouncedName ? searchPath || undefined : undefined,
      path: currentPath || undefined,
      content_kind: contentKindFilter || undefined,
      extension: extensionFilter || undefined,
      status: statusFilter || undefined,
      document_class: debouncedDocumentClass || undefined,
      extraction_schema: debouncedExtractionSchema || undefined,
      extraction_field: debouncedExtractionField || undefined,
      field_filters: serializedFieldFilters,
      review_status: reviewStatusFilter || undefined,
      stale_enrichment: staleOnly || undefined,
    }),
    [
      contentKindFilter,
      currentPath,
      debouncedDocumentClass,
      debouncedExtractionField,
      debouncedExtractionSchema,
      debouncedName,
      extensionFilter,
      nameRegex,
      reviewStatusFilter,
      serializedFieldFilters,
      searchPath,
      staleOnly,
      statusFilter,
    ],
  );

  useEffect(() => {
    onDocumentClassFilterChange?.(debouncedDocumentClass);
  }, [debouncedDocumentClass, onDocumentClassFilterChange]);

  useEffect(() => {
    onExtractionSchemaFilterChange?.(debouncedExtractionSchema);
  }, [debouncedExtractionSchema, onExtractionSchemaFilterChange]);

  useEffect(() => {
    onExtractionFieldFilterChange?.(debouncedExtractionField);
  }, [debouncedExtractionField, onExtractionFieldFilterChange]);

  useEffect(() => {
    onFieldFiltersChange?.(serializedFieldFilters ?? "");
  }, [serializedFieldFilters, onFieldFiltersChange]);

  useEffect(() => {
    onActiveFiltersChange?.(currentBatchFilters);
  }, [currentBatchFilters, onActiveFiltersChange]);

  const handleToggleSort = useCallback((column: SortBy) => {
    setSortBy((currentSortBy) => {
      if (currentSortBy === column) {
        setSortOrder((currentSortOrder) => (currentSortOrder === "asc" ? "desc" : "asc"));
        return currentSortBy;
      }
      setSortOrder("asc");
      return column;
    });
  }, []);

  const handleToggleStaleOnly = useCallback(() => {
    setStaleOnly((current) => {
      const next = !current;
      onStaleOnlyChange?.(next);
      return next;
    });
  }, [onStaleOnlyChange]);

  const handleStatusFilterChange = useCallback(
    (nextStatus: string) => {
      setStatusFilter(nextStatus);
      onStatusFilterChange?.(nextStatus);
    },
    [onStatusFilterChange],
  );

  const handleReviewStatusFilterChange = useCallback(
    (nextStatus: ContentEnrichmentReviewStatus | "") => {
      setReviewStatusFilter(nextStatus);
      onReviewStatusFilterChange?.(nextStatus);
    },
    [onReviewStatusFilterChange],
  );

  const handleSetExtractionFieldFocus = useCallback((field: string) => {
    setExtractionFieldFilter(field);
  }, []);

  const handleAddFieldCondition = useCallback((predicate: FieldFilterPredicate) => {
    setFieldPredicates((current) => [...current, predicate]);
    setExtractionFieldFilter(topLevelField(predicate.segments));
  }, []);

  const handleUpdateFieldCondition = useCallback(
    (index: number, patch: Partial<FieldFilterPredicate>) => {
      setFieldPredicates((current) =>
        current.map((predicate, i) => (i === index ? { ...predicate, ...patch } : predicate)),
      );
    },
    [],
  );

  const handleRemoveFieldCondition = useCallback((index: number) => {
    setFieldPredicates((current) => current.filter((_, i) => i !== index));
  }, []);

  const activeFilterChips = useMemo<ContentListFilterChip[]>(() => {
    const chips: ContentListFilterChip[] = [];
    if (debouncedName.trim()) {
      chips.push({
        kind: "name",
        value: [debouncedName.trim(), nameRegex ? "regex" : "", searchPath ? "path" : ""]
          .filter(Boolean)
          .join(" / "),
        remove: () => setNameFilter(""),
      });
    }
    if (contentKindFilter) {
      chips.push({
        kind: "content_kind",
        value: contentKindFilter,
        remove: () => setContentKindFilter(""),
      });
    }
    if (debouncedDocumentClass.trim()) {
      chips.push({
        kind: "document_class",
        value: debouncedDocumentClass.trim(),
        remove: () => setDocumentClassFilter(""),
      });
    }
    if (debouncedExtractionSchema.trim()) {
      chips.push({
        kind: "extraction_schema",
        value: debouncedExtractionSchema.trim(),
        remove: () => setExtractionSchemaFilter(""),
      });
    }
    if (extensionFilter) {
      chips.push({
        kind: "extension",
        value: extensionFilter,
        remove: () => setExtensionFilter(""),
      });
    }
    if (statusFilter) {
      chips.push({
        kind: "status",
        value: statusFilter,
        remove: () => {
          setStatusFilter("");
          onStatusFilterChange?.("");
        },
      });
    }
    if (reviewStatusFilter) {
      chips.push({
        kind: "review_status",
        value: reviewStatusFilter,
        remove: () => {
          setReviewStatusFilter("");
          onReviewStatusFilterChange?.("");
        },
      });
    }
    if (staleOnly) {
      chips.push({
        kind: "stale_enrichment",
        value: "true",
        remove: () => {
          setStaleOnly(false);
          onStaleOnlyChange?.(false);
        },
      });
    }
    return chips;
  }, [
    contentKindFilter,
    debouncedDocumentClass,
    debouncedExtractionSchema,
    debouncedName,
    extensionFilter,
    nameRegex,
    onReviewStatusFilterChange,
    onStaleOnlyChange,
    onStatusFilterChange,
    reviewStatusFilter,
    searchPath,
    staleOnly,
    statusFilter,
  ]);

  const hasAnyFilter = activeFilterChips.length > 0 || fieldPredicates.length > 0;

  return {
    nameFilter,
    setNameFilter,
    nameRegex,
    setNameRegex,
    searchPath,
    setSearchPath,
    contentKindFilter,
    setContentKindFilter,
    documentClassFilter,
    setDocumentClassFilter,
    extractionSchemaFilter,
    setExtractionSchemaFilter,
    extractionFieldFilter,
    setExtractionFieldFocus: handleSetExtractionFieldFocus,
    fieldPredicates,
    addFieldCondition: handleAddFieldCondition,
    updateFieldCondition: handleUpdateFieldCondition,
    removeFieldCondition: handleRemoveFieldCondition,
    extensionFilter,
    setExtensionFilter,
    statusFilter,
    staleOnly,
    reviewStatusFilter,
    setReviewStatusFilter,
    sortBy,
    sortOrder,
    fetchParams,
    currentBatchFilters,
    handleToggleSort,
    handleToggleStaleOnly,
    handleStatusFilterChange,
    handleReviewStatusFilterChange,
    hasAnyFilter,
    activeFilterChips,
  };
}

export type { FieldFilterDtype, FieldFilterPredicate };
