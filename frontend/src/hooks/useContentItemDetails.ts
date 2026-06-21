import { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNotify, useRefresh } from "@/lib/app-context";
import {
  contentApi,
  type ContentReviewSubmitPayload,
  type ContentItemInfo,
  type ContentItemChunksResponse,
  type ExtractedAssetsResponse,
} from "@/dataProvider";
import { isTerminalContentProcessingStatus } from "@/lib/content-processing";
import { queryKeys } from "@/lib/query-client";
import { reportClientError } from "@/lib/report-client-error";

export type ProcessingConfigPayload = Record<string, unknown>;
export type ContentItemProcessHandler = (
  path: string,
  processingConfig?: ProcessingConfigPayload,
) => Promise<boolean> | boolean;

export type ProcessingConfigFormState = {
  doOcr: boolean;
  doTableStructure: boolean;
  forceFullPageOcr: boolean;
  ocrLang: string;
  tableStructureMode: string;
  imagesScale: string;
  imageExportDpi: string;
  documentEnrichment: boolean;
};

export type ProcessingConfigPayloadBuildResult =
  | { ok: true; payload: ProcessingConfigPayload }
  | { ok: false; messageKey: string };

export const DEFAULT_PROCESSING_CONFIG_FORM: ProcessingConfigFormState = {
  doOcr: true,
  doTableStructure: true,
  forceFullPageOcr: false,
  ocrLang: "",
  tableStructureMode: "",
  imagesScale: "2",
  imageExportDpi: "300",
  documentEnrichment: false,
};

export type ProcessingConfigPresetId = "fast" | "balanced" | "thorough";

export const PROCESSING_CONFIG_PRESET_IDS: readonly ProcessingConfigPresetId[] = [
  "fast",
  "balanced",
  "thorough",
];

const PROCESSING_CONFIG_PRESETS: Record<ProcessingConfigPresetId, ProcessingConfigPayload> = {
  fast: {
    do_ocr: false,
    do_table_structure: false,
    force_full_page_ocr: false,
    document_enrichment: false,
    images_scale: 1,
    image_export_dpi: 200,
  },
  balanced: {
    do_ocr: true,
    do_table_structure: true,
    force_full_page_ocr: false,
    document_enrichment: true,
    table_structure_mode: "fast",
    images_scale: 2,
    image_export_dpi: 300,
  },
  thorough: {
    do_ocr: true,
    do_table_structure: true,
    force_full_page_ocr: true,
    document_enrichment: true,
    table_structure_mode: "accurate",
    images_scale: 2,
    image_export_dpi: 300,
  },
};

export function buildPresetProcessingConfig(
  preset: ProcessingConfigPresetId,
): ProcessingConfigPayload {
  return { ...PROCESSING_CONFIG_PRESETS[preset] };
}

export function buildCustomProcessingConfigPayload(
  form: ProcessingConfigFormState,
): ProcessingConfigPayloadBuildResult {
  const payload: ProcessingConfigPayload = {
    do_ocr: form.doOcr,
    do_table_structure: form.doTableStructure,
    force_full_page_ocr: form.forceFullPageOcr,
    document_enrichment: form.documentEnrichment,
  };

  const langParts = form.ocrLang
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (langParts.length === 1) {
    payload.ocr_lang = langParts[0];
  } else if (langParts.length > 1) {
    payload.ocr_lang = langParts;
  }

  if (form.tableStructureMode) {
    payload.table_structure_mode = form.tableStructureMode;
  }

  const imagesScale = Number.parseFloat(form.imagesScale);
  if (form.imagesScale.trim() !== "" && !Number.isFinite(imagesScale)) {
    return {
      ok: false,
      messageKey: "custom.content.processing_config.invalid_images_scale",
    };
  }
  if (Number.isFinite(imagesScale)) {
    payload.images_scale = imagesScale;
  }

  const imageExportDpi = Number.parseFloat(form.imageExportDpi);
  if (Number.isFinite(imageExportDpi)) {
    payload.image_export_dpi = imageExportDpi;
  }

  return { ok: true, payload };
}

export function parseFormFromLastConfig(
  raw: Record<string, unknown> | null | undefined,
): ProcessingConfigFormState {
  if (!raw) {
    return { ...DEFAULT_PROCESSING_CONFIG_FORM };
  }

  const ocrLangRaw = raw.ocr_lang;
  let ocrLang = "";
  if (typeof ocrLangRaw === "string") {
    ocrLang = ocrLangRaw;
  } else if (Array.isArray(ocrLangRaw)) {
    ocrLang = ocrLangRaw.filter((item) => typeof item === "string").join(", ");
  }

  const imagesScaleRaw = raw.images_scale;
  const imagesScale =
    typeof imagesScaleRaw === "number" && Number.isFinite(imagesScaleRaw)
      ? String(imagesScaleRaw)
      : DEFAULT_PROCESSING_CONFIG_FORM.imagesScale;

  const imageExportDpiRaw = raw.image_export_dpi;
  const imageExportDpi =
    typeof imageExportDpiRaw === "number" && Number.isFinite(imageExportDpiRaw)
      ? String(imageExportDpiRaw)
      : DEFAULT_PROCESSING_CONFIG_FORM.imageExportDpi;

  return {
    doOcr: typeof raw.do_ocr === "boolean" ? raw.do_ocr : DEFAULT_PROCESSING_CONFIG_FORM.doOcr,
    doTableStructure:
      typeof raw.do_table_structure === "boolean"
        ? raw.do_table_structure
        : DEFAULT_PROCESSING_CONFIG_FORM.doTableStructure,
    forceFullPageOcr:
      typeof raw.force_full_page_ocr === "boolean"
        ? raw.force_full_page_ocr
        : DEFAULT_PROCESSING_CONFIG_FORM.forceFullPageOcr,
    ocrLang,
    tableStructureMode:
      typeof raw.table_structure_mode === "string"
        ? raw.table_structure_mode
        : DEFAULT_PROCESSING_CONFIG_FORM.tableStructureMode,
    imagesScale,
    imageExportDpi,
    documentEnrichment:
      typeof raw.document_enrichment === "boolean"
        ? raw.document_enrichment
        : DEFAULT_PROCESSING_CONFIG_FORM.documentEnrichment,
  };
}

export const useContentItemDetails = (initialFile: ContentItemInfo | null, open: boolean) => {
  const notify = useNotify();
  const refresh = useRefresh();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<ContentItemInfo | null>(initialFile);
  const [chunksData, setChunksData] = useState<ContentItemChunksResponse | null>(null);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [extractedData, setExtractedData] = useState<ExtractedAssetsResponse | null>(null);
  const [extractedLoading, setExtractedLoading] = useState(false);
  const [reprocessingTriggered, setReprocessingTriggered] = useState(false);
  const [savingEnrichment, setSavingEnrichment] = useState(false);
  const currentFilePath = file?.path;

  const isProcessing = useMemo(() => {
    if (!file) return false;
    return (
      file.status === "QUEUED" ||
      file.status === "PROCESSING" ||
      file.status === "RETRYING" ||
      reprocessingTriggered
    );
  }, [file, reprocessingTriggered]);

  const fetchData = useCallback(async (filePath: string) => {
    setExtractedLoading(true);
    try {
      const data = await contentApi.getExtractedAssets(filePath);
      setExtractedData(data);
    } catch (error) {
      reportClientError(error, undefined, { routeName: "content-item-details:extracted-assets" });
      setExtractedData({
        file_path: filePath,
        figures: [],
        tables: [],
        has_extracted_content: false,
        has_docling_document: false,
      });
    } finally {
      setExtractedLoading(false);
    }
  }, []);

  const fetchChunks = useCallback(async (filePath: string) => {
    setChunksLoading(true);
    try {
      const data = await contentApi.getChunks(filePath);
      setChunksData(data);
    } catch (error) {
      reportClientError(error, undefined, { routeName: "content-item-details:chunks" });
      setChunksData({
        file_path: filePath,
        chunks: [],
        total_chunks: 0,
        is_indexed: false,
      });
    } finally {
      setChunksLoading(false);
    }
  }, []);

  const fileQuery = useQuery({
    queryKey: currentFilePath
      ? queryKeys.content.details(currentFilePath)
      : [...queryKeys.content.all, "details", "none"],
    enabled: open && Boolean(currentFilePath),
    queryFn: () => contentApi.getDetails(currentFilePath ?? ""),
    refetchInterval: isProcessing ? 3000 : false,
  });

  const refreshFile = useCallback(
    async (filePath: string) => {
      const updatedFile = await queryClient.fetchQuery({
        queryKey: queryKeys.content.details(filePath),
        queryFn: () => contentApi.getDetails(filePath),
      });
      setFile(updatedFile);
      return updatedFile;
    },
    [queryClient],
  );

  useEffect(() => {
    if (initialFile) {
      setFile(initialFile);
    }
  }, [initialFile]);

  useEffect(() => {
    if (!fileQuery.data) {
      return;
    }
    setFile(fileQuery.data);
    if (isTerminalContentProcessingStatus(fileQuery.data.status)) {
      setReprocessingTriggered(false);
    }
  }, [fileQuery.data, fileQuery.dataUpdatedAt]);

  useEffect(() => {
    if (open && initialFile) {
      setChunksData(null);
      setExtractedData(null);
      setReprocessingTriggered(false);
      fetchData(initialFile.path);
    }
  }, [open, initialFile, fetchData]);

  useEffect(() => {
    if (!fileQuery.data || !isTerminalContentProcessingStatus(fileQuery.data.status)) {
      return;
    }
    fetchData(fileQuery.data.path);
    setChunksData(null);
  }, [fetchData, fileQuery.data, fileQuery.dataUpdatedAt]);

  const handleAbort = async () => {
    if (!file) return;
    try {
      await contentApi.abortProcessing(file.id);
      notify("custom.content.actions.aborted_success", { type: "info" });

      const updatedFile = await refreshFile(file.path);
      setFile(updatedFile);
      setReprocessingTriggered(false);
      refresh();
    } catch (error) {
      reportClientError(error, undefined, { routeName: "content-item-details:abort" });
      notify("custom.content.actions.aborted_failed", { type: "error" });
    }
  };

  const verifyClass = useCallback(
    async (classificationLabel: string) => {
      if (!file) {
        throw new Error("No file selected");
      }
      setSavingEnrichment(true);
      try {
        const result = await contentApi.verifyClass(file.path, {
          classification_label: classificationLabel,
        });
        setFile(result.content_item);
        if (result.task_id) {
          setReprocessingTriggered(true);
        }
        refresh();
        return result;
      } finally {
        setSavingEnrichment(false);
      }
    },
    [file, refresh],
  );

  const submitReview = useCallback(
    async (payload: ContentReviewSubmitPayload) => {
      if (!file) {
        throw new Error("No file selected");
      }
      setSavingEnrichment(true);
      try {
        const updatedFile = await contentApi.submitReview(file.path, payload);
        setFile(updatedFile);
        refresh();
        return updatedFile;
      } finally {
        setSavingEnrichment(false);
      }
    },
    [file, refresh],
  );

  const loadFile = useCallback(
    async (filePath: string) => {
      const updatedFile = await contentApi.getDetails(filePath);
      setFile(updatedFile);
      setChunksData(null);
      setExtractedData(null);
      setReprocessingTriggered(false);
      await fetchData(updatedFile.path);
      return updatedFile;
    },
    [fetchData],
  );

  return {
    file,
    setFile,
    loadFile,
    chunksData,
    chunksLoading,
    fetchChunks,
    extractedData,
    extractedLoading,
    isProcessing,
    savingEnrichment,
    setReprocessingTriggered,
    handleAbort,
    verifyClass,
    submitReview,
    refreshData: fetchData,
  };
};
