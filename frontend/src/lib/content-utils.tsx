import {
  FileText,
  File,
  Image as ImageIcon,
  Film,
  Music,
  Folder,
  Mail,
  Paperclip,
} from "lucide-react";
import type { ContentItemInfo, ContentItemKind, FolderInfo } from "@/dataProvider";

export const formatDate = (dateStr?: string) => {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const formatDuration = (ms?: number | null) => {
  if (ms === undefined || ms === null) return "-";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
};

export const formatSize = (bytes?: number) => {
  if (bytes === undefined || bytes === null) return "-";
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

export const getFileIcon = (extension?: string) => {
  const ext = extension?.toLowerCase().replace(".", "");
  switch (ext) {
    case "folder":
      return <Folder className="h-5 w-5 text-muted-foreground" />;
    case "pdf":
    case "doc":
    case "docx":
    case "txt":
    case "md":
      return <FileText className="h-5 w-5 text-muted-foreground" />;
    case "jpg":
    case "jpeg":
    case "png":
    case "gif":
    case "webp":
    case "svg":
      return <ImageIcon className="h-5 w-5 text-muted-foreground" />;
    case "mp4":
    case "avi":
    case "mov":
    case "mkv":
    case "webm":
      return <Film className="h-5 w-5 text-muted-foreground" />;
    case "mp3":
    case "m4a":
    case "wav":
    case "flac":
      return <Music className="h-5 w-5 text-muted-foreground" />;
    default:
      return <File className="h-5 w-5 text-muted-foreground" />;
  }
};

export const getContentItemIcon = (kind?: ContentItemKind | null, extension?: string | null) => {
  if (kind === "folder") {
    return <Folder className="h-5 w-5 text-muted-foreground" />;
  }
  if (kind === "email_message") {
    return <Mail className="h-5 w-5 text-muted-foreground" />;
  }
  if (kind === "attachment") {
    const attachmentIcon = getFileIcon(extension ?? undefined);
    return extension ? attachmentIcon : <Paperclip className="h-5 w-5 text-muted-foreground" />;
  }
  return getFileIcon(extension ?? undefined);
};

export const getContentItemDisplayName = (
  item:
    | Pick<ContentItemInfo, "display_name" | "name" | "path">
    | Pick<FolderInfo, "display_name" | "name" | "path">,
): string => item.display_name || item.name || item.path;

export const getContentRelationshipHint = (
  item: Pick<ContentItemInfo, "kind" | "parent_item" | "child_items">,
  translate: (key: string, options?: Record<string, unknown>) => string,
): string | null => {
  if (item.kind === "attachment" && item.parent_item?.display_name) {
    return translate("custom.content.search.attachment_parent", {
      name: item.parent_item.display_name,
    });
  }
  if (item.kind === "email_message" && item.child_items && item.child_items.length > 0) {
    return translate("custom.content.search.email_attachments_count", {
      smart_count: item.child_items.length,
    });
  }
  return null;
};

export const getContentItemContextHints = (
  item: Pick<ContentItemInfo, "kind" | "parent_item" | "child_items" | "email_message_details">,
  translate: (key: string, options?: Record<string, unknown>) => string,
): string[] => {
  const hints: string[] = [];
  const relationshipHint = getContentRelationshipHint(item, translate);
  if (relationshipHint) {
    hints.push(relationshipHint);
  }

  if (item.kind === "email_message" && item.email_message_details) {
    const fromAddress = item.email_message_details.from_address?.trim();
    if (fromAddress) {
      hints.push(
        translate("custom.content.search.email_from", {
          address: fromAddress,
        }),
      );
    }
    if (item.email_message_details.sent_at) {
      hints.push(
        translate("custom.content.search.email_sent_at", {
          date: formatDate(String(item.email_message_details.sent_at)),
        }),
      );
    }
  }

  return hints;
};

const EXCEL_EXTENSIONS = new Set(["xlsx", "xls"]);
const MARKDOWN_EXTENSIONS = new Set(["md", "markdown", "mdown"]);

export const isExcelFile = (extension?: string): boolean => {
  const ext = extension?.toLowerCase().replace(".", "");
  return EXCEL_EXTENSIONS.has(ext || "");
};

export const isDocxFile = (extension?: string): boolean => {
  const ext = extension?.toLowerCase().replace(".", "");
  return ext === "docx";
};

export const isMarkdownFile = (extension?: string): boolean => {
  const ext = extension?.toLowerCase().replace(".", "");
  return MARKDOWN_EXTENSIONS.has(ext || "");
};

export const getPreviewType = (
  extension?: string,
): "pdf" | "document" | "image" | "text" | "video" | "audio" | null => {
  const ext = extension?.toLowerCase().replace(".", "");
  if (ext === "pdf") return "pdf";
  if (["doc", "docx", "xlsx", "xls", "pptx"].includes(ext || "")) return "document";
  if (["jpg", "jpeg", "png", "gif", "webp", "svg"].includes(ext || "")) return "image";
  if (["mp4", "webm", "mov", "ogg"].includes(ext || "")) return "video";
  if (["mp3", "m4a", "wav", "ogg", "flac", "aac"].includes(ext || "")) return "audio";
  if (
    [
      "txt",
      "md",
      "markdown",
      "mdown",
      "json",
      "xml",
      "html",
      "css",
      "js",
      "py",
      "yaml",
      "yml",
      "toml",
      "ini",
      "log",
      "csv",
    ].includes(ext || "")
  )
    return "text";
  return null;
};
