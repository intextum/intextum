import type { ConversationSource } from "@/dataProvider";

export interface ChatPanelSource extends ConversationSource {
  preview_images: string[];
}

type SourceLike = {
  file_path: string;
  display_name?: string | null;
  content_kind?: "file" | "folder" | "email_message" | "attachment" | null;
  email_from_address?: string | null;
  email_sent_at?: string | null;
  parent_display_name?: string | null;
  title?: string | null;
  source_kind?: string | null;
};

const uniqueNumbers = (values: number[]): number[] => {
  const deduped: number[] = [];
  const seen = new Set<number>();
  for (const value of values) {
    if (seen.has(value)) {
      continue;
    }
    deduped.push(value);
    seen.add(value);
  }
  return deduped;
};

const uniqueStrings = (values: string[]): string[] => {
  const deduped: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    deduped.push(value);
    seen.add(value);
  }
  return deduped;
};

const uniqueImages = (images: string[]): string[] => {
  return uniqueStrings(images);
};

const filenameFromPath = (filePath: string): string => filePath.split("/").pop() || filePath;

const fallbackDisplayName = (source: SourceLike): string =>
  source.display_name?.trim() || filenameFromPath(source.file_path);

const mergeChatPanelSources = (
  left: ChatPanelSource,
  right: ConversationSource,
): ChatPanelSource => {
  return {
    ...left,
    page_numbers: uniqueNumbers([...left.page_numbers, ...right.page_numbers]),
    doc_refs: uniqueStrings([...left.doc_refs, ...right.doc_refs]),
    images: uniqueImages([...left.images, ...(right.images ?? [])]),
    preview_images: uniqueImages([...left.preview_images, ...(right.images ?? [])]),
  };
};

export const buildChatPanelSources = (sources: ConversationSource[]): ChatPanelSource[] => {
  const numbered: ChatPanelSource[] = [];
  const unnumberedByContentKey = new Map<string, ChatPanelSource>();

  for (const source of sources) {
    const normalized: ChatPanelSource = {
      ...source,
      preview_images: uniqueImages(source.images ?? []),
    };

    if (typeof source.citation_index === "number") {
      numbered.push(normalized);
      continue;
    }

    const dedupeKey = source.content_item_id || source.file_path;
    const existing = unnumberedByContentKey.get(dedupeKey);
    unnumberedByContentKey.set(
      dedupeKey,
      existing ? mergeChatPanelSources(existing, source) : normalized,
    );
  }

  numbered.sort((a, b) => (a.citation_index ?? 0) - (b.citation_index ?? 0));
  return [...numbered, ...unnumberedByContentKey.values()];
};

export const sourceDisplayTitle = (source: SourceLike): string =>
  source.title?.trim() || fallbackDisplayName(source);

export const sourceDisplayPath = (source: SourceLike): string | null =>
  source.title?.trim() && source.title.trim() !== fallbackDisplayName(source)
    ? source.file_path
    : null;

export const sourceContextLine = (
  source: SourceLike,
  translate: (key: string, options?: unknown) => string,
): string | null => {
  if (source.content_kind === "email_message") {
    const parts: string[] = [];
    if (source.email_from_address?.trim()) {
      parts.push(
        translate("custom.content.search.email_from", {
          address: source.email_from_address.trim(),
        }),
      );
    }
    if (source.email_sent_at) {
      const formattedDate = new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(source.email_sent_at));
      parts.push(
        translate("custom.content.search.email_sent_at", {
          date: formattedDate,
        }),
      );
    }
    return parts.length > 0 ? parts.join(" • ") : null;
  }

  if (source.content_kind === "attachment" && source.parent_display_name?.trim()) {
    return translate("custom.content.search.attachment_parent", {
      name: source.parent_display_name.trim(),
    });
  }

  return null;
};

export const isReviewedEnrichmentSource = (source: SourceLike): boolean =>
  source.source_kind === "reviewed_enrichment";
