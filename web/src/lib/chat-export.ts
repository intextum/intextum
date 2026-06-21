import type {
  AssistantResponseExportPayload,
  ConversationMessage,
  ExportEmbeddedImagePayload,
  ResearchReportDetail,
  ResearchReportImage,
  ResearchReportMessageMetadata,
} from "../dataProvider.ts";

export interface ExportLabels {
  assistantDefaultTitle: string;
  assistantLabel: string;
  conversationDefaultTitle: string;
  contextFilesHeading: string;
  imagesHeading: string;
  researchDefaultTitle: string;
  sourcesHeading: string;
  userLabel: string;
  verificationHeading: string;
}

export interface ExportDocument {
  filenameBase: string;
  markdown: string;
  title: string;
}

export interface ExportUrlOptions {
  absoluteBaseUrl?: string;
}

export interface MarkdownImageReference {
  altText: string;
  url: string;
}

interface ExportSourceLike {
  file_path: string;
  display_name?: string | null;
  title?: string | null;
  page_numbers: number[];
  doc_refs: string[];
  citation_index?: number | null;
  images?: string[];
  quote?: string | null;
}

const HEADING_PATTERN = /^\s*#\s+(.+?)\s*$/m;
const INLINE_CODE_PATTERN = /`([^`]+)`/g;
const INLINE_IMAGE_PATTERN = /!\[([^\]]*)\]\(([^)]+)\)/g;
const INLINE_LINK_PATTERN = /\[([^\]]+)\]\(([^)]+)\)/g;
const INLINE_TEXT_LINK_PATTERN = /(^|[^!])\[([^\]]+)\]\(([^)]+)\)/g;
const EMPHASIS_PATTERNS = [
  /\*\*(.+?)\*\*/g,
  /__(.+?)__/g,
  /(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)/g,
  /(?<!_)_(?!\s)(.+?)(?<!\s)_(?!_)/g,
];
const FILENAME_FORBIDDEN_CHARACTERS = new Set(["\\", "/", ":", "*", "?", '"', "<", ">", "|"]);

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const normalizeMarkdown = (value: string): string => value.replace(/\r\n/g, "\n").trim();

const normalizeBaseUrl = (value?: string): string | undefined => {
  const trimmed = value?.trim();
  if (!trimmed) {
    return undefined;
  }
  return trimmed.replace(/\/+$/g, "");
};

const shiftMarkdownHeadings = (markdown: string, levelDelta: number): string =>
  normalizeMarkdown(markdown).replace(
    /^(#{1,6})(\s+)/gm,
    (_fullMatch, hashes: string, whitespace: string) => {
      const nextLevel = Math.min(6, hashes.length + levelDelta);
      return `${"#".repeat(nextLevel)}${whitespace}`;
    },
  );

const stripSecondLevelSections = (markdown: string, headingsToStrip: string[]): string => {
  const normalized = normalizeMarkdown(markdown);
  if (!normalized) {
    return normalized;
  }

  const strippedHeadings = new Set(
    headingsToStrip.map((heading) => heading.trim().toLocaleLowerCase()),
  );
  const lines = normalized.split("\n");
  const keptLines: string[] = [];
  let skipSection = false;

  for (const line of lines) {
    const headingMatch = line.match(/^##\s+(.+?)\s*$/);
    if (headingMatch) {
      skipSection = strippedHeadings.has(headingMatch[1].trim().toLocaleLowerCase());
      if (skipSection) {
        continue;
      }
    }

    if (!skipSection) {
      keptLines.push(line);
    }
  }

  return keptLines.join("\n").trim();
};

const hasTopLevelHeading = (markdown: string): boolean => {
  const normalized = normalizeMarkdown(markdown);
  if (!normalized) {
    return false;
  }
  const firstNonEmptyLine = normalized.split("\n").find((line) => line.trim().length > 0) ?? "";
  return /^#\s+/.test(firstNonEmptyLine.trim());
};

const flattenMarkdownText = (value: string): string => {
  let flattened = value.replace(/\\\[/g, "[").replace(/\\\]/g, "]");
  flattened = flattened.replace(
    INLINE_IMAGE_PATTERN,
    (_match, alt: string, url: string) => `${(alt || "Image").trim()} (${url.trim()})`,
  );
  flattened = flattened.replace(
    INLINE_LINK_PATTERN,
    (_match, label: string, url: string) => `${label.trim()} (${url.trim()})`,
  );
  flattened = flattened.replace(INLINE_CODE_PATTERN, (_match, code: string) => code);
  for (const pattern of EMPHASIS_PATTERNS) {
    flattened = flattened.replace(pattern, (_match, text: string) => text);
  }
  return flattened.replace(/\s+/g, " ").trim();
};

const deriveTitleFromMarkdown = (markdown: string, fallback: string): string => {
  const normalized = normalizeMarkdown(markdown);
  const headingMatch = normalized.match(HEADING_PATTERN);
  if (headingMatch) {
    return flattenMarkdownText(headingMatch[1]) || fallback;
  }

  const firstMeaningfulLine =
    normalized
      .split("\n")
      .map((line) => flattenMarkdownText(line))
      .find((line) => line.length > 0) ?? "";
  if (!firstMeaningfulLine) {
    return fallback;
  }
  return firstMeaningfulLine.length <= 80
    ? firstMeaningfulLine
    : `${firstMeaningfulLine.slice(0, 77).trimEnd()}...`;
};

export const sanitizeExportFilenameBase = (value: string, fallback: string): string => {
  const sanitized = value
    .replace(/./g, (char) =>
      char <= "\u001f" || FILENAME_FORBIDDEN_CHARACTERS.has(char) ? "-" : char,
    )
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[ ._-]+|[ ._-]+$/g, "");
  return sanitized || fallback;
};

const toAbsoluteUrl = (value: string, options?: ExportUrlOptions): string => {
  if (!value) {
    return value;
  }

  const baseUrl = normalizeBaseUrl(options?.absoluteBaseUrl);
  if (!baseUrl) {
    return value;
  }

  try {
    return new URL(value).toString();
  } catch {
    return new URL(value.startsWith("/") ? value : `/${value}`, `${baseUrl}/`).toString();
  }
};

const canonicalizeExportUrl = (value: string, options?: ExportUrlOptions): string => {
  const trimmed = value.trim();
  if (!trimmed) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed);
    if (url.pathname.startsWith("/api/content/download/")) {
      url.pathname = url.pathname.replace("/api/content/download/", "/api/content/preview/");
    }
    return url.toString();
  } catch {
    const path = trimmed.startsWith("/api/content/download/")
      ? trimmed.replace("/api/content/download/", "/api/content/preview/")
      : trimmed;
    return toAbsoluteUrl(path, options);
  }
};

const rewriteMarkdownUrls = (markdown: string, options?: ExportUrlOptions): string => {
  let rewritten = normalizeMarkdown(markdown);
  rewritten = rewritten.replace(
    INLINE_IMAGE_PATTERN,
    (_match, alt: string, url: string) => `![${alt}](${canonicalizeExportUrl(url, options)})`,
  );
  rewritten = rewritten.replace(
    INLINE_TEXT_LINK_PATTERN,
    (_match, prefix: string, label: string, url: string) =>
      `${prefix}[${label}](${canonicalizeExportUrl(url, options)})`,
  );
  return rewritten;
};

const sourcePreviewUrl = (filePath: string, options?: ExportUrlOptions): string =>
  toAbsoluteUrl(`/api/content/preview/${encodeURIComponent(filePath)}`, options);

const extractContextPathsFromMessage = (message: ConversationMessage): string[] => {
  const metadata = message.metadata;
  if (!isObjectRecord(metadata) || !Array.isArray(metadata.context_file_paths)) {
    return [];
  }

  return metadata.context_file_paths.filter((item): item is string => typeof item === "string");
};

const researchReportFromMessage = (
  message: ConversationMessage,
): ResearchReportMessageMetadata | null => {
  const metadata = message.metadata;
  if (
    !metadata ||
    typeof metadata !== "object" ||
    metadata.kind !== "research_report" ||
    !Array.isArray((metadata as { sections?: unknown }).sections) ||
    !Array.isArray((metadata as { sources?: unknown }).sources)
  ) {
    return null;
  }
  return metadata as unknown as ResearchReportMessageMetadata;
};

const sourceLabel = (source: ExportSourceLike): string =>
  source.title || source.display_name || source.file_path.split("/").pop() || source.file_path;

const sourceLineWithUrls = (source: ExportSourceLike, options?: ExportUrlOptions): string => {
  const prefix = typeof source.citation_index === "number" ? `- [${source.citation_index}] ` : "- ";
  const pageText =
    source.page_numbers.length > 0 ? ` (pages ${source.page_numbers.join(", ")})` : "";
  return `${prefix}${sourceLabel(source)}: [${source.file_path}](${sourcePreviewUrl(source.file_path, options)})${pageText}`;
};

const sourceQuoteLine = (source: ExportSourceLike): string | null =>
  source.quote?.trim() ? `  > ${source.quote.trim()}` : null;

const appendSection = (parts: string[], heading: string, lines: string[]): void => {
  if (lines.length === 0) {
    return;
  }
  parts.push(`## ${heading}`, "", ...lines, "");
};

const buildSourcesSection = (sources: ExportSourceLike[], options?: ExportUrlOptions): string[] => {
  const lines: string[] = [];
  for (const source of sources) {
    lines.push(sourceLineWithUrls(source, options));
    const quoteLine = sourceQuoteLine(source);
    if (quoteLine) {
      lines.push(quoteLine);
    }
  }
  return lines;
};

const buildImagesSection = (
  images: ResearchReportImage[],
  options?: ExportUrlOptions,
): string[] => {
  const lines: string[] = [];
  for (const image of images) {
    const prefix = typeof image.citation_index === "number" ? `- [${image.citation_index}] ` : "- ";
    const label = image.title?.trim() || "Image";
    const absoluteUrl = toAbsoluteUrl(image.url, options);
    lines.push(`${prefix}[${label}](${absoluteUrl})`);
    lines.push(`  ![${label}](${absoluteUrl})`);
  }
  return lines;
};

const ensureMarkdownTitle = (markdown: string, title: string): string =>
  hasTopLevelHeading(markdown)
    ? normalizeMarkdown(markdown)
    : `# ${title}\n\n${normalizeMarkdown(markdown)}`;

const roleLabel = (role: string, labels: ExportLabels): string => {
  if (role === "user") {
    return labels.userLabel;
  }
  if (role === "assistant") {
    return labels.assistantLabel;
  }
  return role.charAt(0).toUpperCase() + role.slice(1);
};

const conversationTitleFromMessages = (
  messages: ConversationMessage[],
  fallback: string,
): string => {
  for (const message of messages) {
    const candidate = deriveTitleFromMarkdown(message.content, "");
    if (candidate) {
      return candidate;
    }
  }
  return fallback;
};

export const buildExportLabels = (
  translate: (key: string, options?: unknown) => string,
): ExportLabels => ({
  assistantDefaultTitle: translate("custom.exports.assistant_default_title"),
  assistantLabel: translate("custom.exports.assistant_label"),
  conversationDefaultTitle: translate("custom.exports.conversation_default_title"),
  contextFilesHeading: translate("custom.exports.context_files_heading"),
  imagesHeading: translate("custom.exports.images_heading"),
  researchDefaultTitle: translate("custom.exports.research_default_title"),
  sourcesHeading: translate("custom.exports.sources_heading"),
  userLabel: translate("custom.exports.user_label"),
  verificationHeading: translate("custom.exports.verification_heading"),
});

export const buildAssistantResponseExportDocument = (
  message: ConversationMessage,
  labels: ExportLabels,
  options?: ExportUrlOptions,
): ExportDocument => {
  const body = rewriteMarkdownUrls(message.content, options);
  const title = deriveTitleFromMarkdown(body, labels.assistantDefaultTitle);
  const parts = [ensureMarkdownTitle(body, title), ""];
  if (!/^##\s+Sources\b/m.test(parts[0])) {
    appendSection(
      parts,
      labels.sourcesHeading,
      buildSourcesSection(message.sources ?? [], options),
    );
  }
  const markdown = parts.join("\n").trim();

  return {
    title,
    filenameBase: sanitizeExportFilenameBase(title, "assistant-response"),
    markdown,
  };
};

export const buildResearchResponseExportDocument = (
  report: ResearchReportDetail,
  labels: ExportLabels,
  options?: ExportUrlOptions,
): ExportDocument => {
  const fallbackTitle = report.title?.trim() || labels.researchDefaultTitle;
  const baseMarkdown = stripSecondLevelSections(
    rewriteMarkdownUrls(report.content_markdown || "", options),
    [labels.sourcesHeading, labels.imagesHeading, labels.verificationHeading],
  );
  const title = report.title?.trim() || deriveTitleFromMarkdown(baseMarkdown, fallbackTitle);

  const parts: string[] = [];
  if (baseMarkdown) {
    parts.push(ensureMarkdownTitle(baseMarkdown, title), "");
  } else {
    parts.push(`# ${title}`, "");
    for (const section of report.sections) {
      parts.push(`## ${section.heading}`, "", normalizeMarkdown(section.body), "");
    }
    appendSection(parts, labels.sourcesHeading, buildSourcesSection(report.sources ?? [], options));
  }

  if (!/^##\s+Sources\b/m.test(parts.join("\n"))) {
    appendSection(parts, labels.sourcesHeading, buildSourcesSection(report.sources ?? [], options));
  }
  appendSection(parts, labels.imagesHeading, buildImagesSection(report.images ?? [], options));
  appendSection(parts, labels.verificationHeading, report.verification.issues ?? []);

  return {
    title,
    filenameBase: sanitizeExportFilenameBase(title, "research-report"),
    markdown: parts.join("\n").trim(),
  };
};

export const buildConversationExportDocument = (
  conversation: {
    messages: ConversationMessage[];
    title?: string | null;
  },
  labels: ExportLabels,
  options?: ExportUrlOptions,
): ExportDocument => {
  const title =
    conversation.title?.trim() ||
    conversationTitleFromMessages(conversation.messages, labels.conversationDefaultTitle);
  const parts: string[] = [`# ${title}`, ""];

  conversation.messages.forEach((message, index) => {
    parts.push(`## ${roleLabel(message.role, labels)} ${index + 1}`, "");

    const researchReport = researchReportFromMessage(message);
    if (researchReport) {
      parts.push(
        shiftMarkdownHeadings(
          buildResearchResponseExportDocument(researchReport, labels, options).markdown,
          2,
        ),
        "",
      );
    } else if (message.content.trim()) {
      parts.push(rewriteMarkdownUrls(message.content, options), "");
    }

    const contextFilePaths = extractContextPathsFromMessage(message);
    appendSection(
      parts,
      labels.contextFilesHeading,
      contextFilePaths.map((path) => `- [${path}](${sourcePreviewUrl(path, options)})`),
    );

    if (!researchReport) {
      appendSection(
        parts,
        labels.sourcesHeading,
        buildSourcesSection(message.sources ?? [], options),
      );
    }
  });

  return {
    title,
    filenameBase: sanitizeExportFilenameBase(title, "conversation"),
    markdown: parts.join("\n").trim(),
  };
};

export const extractMarkdownEmbeddedImages = (markdown: string): MarkdownImageReference[] => {
  const references: MarkdownImageReference[] = [];
  const seenUrls = new Set<string>();
  const imagePattern = new RegExp(INLINE_IMAGE_PATTERN.source, "g");
  for (const match of normalizeMarkdown(markdown).matchAll(imagePattern)) {
    const altText = (match[1] || "Image").trim() || "Image";
    const url = match[2]?.trim();
    if (!url || seenUrls.has(url)) {
      continue;
    }
    seenUrls.add(url);
    references.push({ altText, url });
  }
  return references;
};

const bufferToBase64 = (buffer: ArrayBuffer): string => {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
};

const imageDimensionsFromBlob = async (
  blob: Blob,
): Promise<{ width_px: number; height_px: number }> => {
  if (typeof window.createImageBitmap === "function") {
    const bitmap = await window.createImageBitmap(blob);
    try {
      return { width_px: bitmap.width, height_px: bitmap.height };
    } finally {
      bitmap.close();
    }
  }

  const objectUrl = window.URL.createObjectURL(blob);
  try {
    const dimensions = await new Promise<{ width_px: number; height_px: number }>(
      (resolve, reject) => {
        const image = new window.Image();
        image.onload = () =>
          resolve({
            width_px: image.naturalWidth,
            height_px: image.naturalHeight,
          });
        image.onerror = () => reject(new Error("Failed to decode export image"));
        image.src = objectUrl;
      },
    );
    return dimensions;
  } finally {
    window.URL.revokeObjectURL(objectUrl);
  }
};

const filenameFromImageReference = (
  reference: MarkdownImageReference,
  mediaType: string,
  index: number,
): string => {
  const fallbackExtension = mediaType.split("/")[1] || "bin";
  try {
    const url = new URL(reference.url);
    const pathname = url.pathname.split("/").pop() || "";
    if (pathname) {
      return pathname;
    }
  } catch {
    // Fall back to a synthetic filename below.
  }
  return `${sanitizeExportFilenameBase(reference.altText, `image-${index}`)}.${fallbackExtension}`;
};

const loadEmbeddedExportImages = async (
  markdown: string,
): Promise<ExportEmbeddedImagePayload[]> => {
  const references = extractMarkdownEmbeddedImages(markdown);
  const assets: ExportEmbeddedImagePayload[] = [];

  for (const [index, reference] of references.entries()) {
    try {
      const response = await window.fetch(reference.url, {
        credentials: "include",
      });
      if (!response.ok) {
        continue;
      }
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) {
        continue;
      }
      const { width_px, height_px } = await imageDimensionsFromBlob(blob);
      assets.push({
        url: reference.url,
        filename: filenameFromImageReference(reference, blob.type, index + 1),
        media_type: blob.type,
        data_base64: bufferToBase64(await blob.arrayBuffer()),
        width_px,
        height_px,
        alt_text: reference.altText,
      });
    } catch (error) {
      console.warn("Skipping DOCX embedded image:", reference.url, error);
    }
  }

  return assets;
};

export const buildDocxExportPayload = async (
  document: ExportDocument,
): Promise<AssistantResponseExportPayload> => ({
  title: document.title,
  filename_base: document.filenameBase,
  markdown: document.markdown,
  embedded_images: await loadEmbeddedExportImages(document.markdown),
});

export const downloadBlob = (filename: string, blob: Blob): void => {
  const url = window.URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  window.document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};

export const downloadMarkdownExportDocument = (document: ExportDocument): void => {
  downloadBlob(
    `${document.filenameBase}.md`,
    new Blob([document.markdown], { type: "text/markdown;charset=utf-8" }),
  );
};
