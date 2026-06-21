import type { ContentItemInfo } from "../dataProvider.ts";
import {
  getContentEnrichmentReviewReasons,
  getContentEnrichmentReviewStatus,
  getContentReviewState,
  hasNeedsReviewContentEnrichment,
  type ContentEnrichmentReviewReason,
} from "./content-enrichment.ts";

export type StatusSeverity = "neutral" | "info" | "success" | "warning" | "error";
export type StatusIconName = "alert" | "check" | "clock" | "inbox" | "loader" | "refresh";
export type StatusBadgeVariant = "default" | "secondary" | "outline" | "destructive";

export interface StatusPresentation {
  labelKey: string;
  shortLabelKey?: string;
  descriptionKey: string;
  actionKey?: string;
  severity: StatusSeverity;
  icon: StatusIconName;
  badgeVariant: StatusBadgeVariant;
}

export interface ReviewStatePresentation extends StatusPresentation {
  status: "reviewed" | "needs_review" | "stale" | "none";
  reasons: ContentEnrichmentReviewReason[];
}

export type ContentStatusPresentation = StatusPresentation;

const CONTENT_STATUS_PRESENTATIONS: Record<string, StatusPresentation> = {
  QUEUED: {
    labelKey: "custom.content.status.queued",
    descriptionKey: "custom.status_presentations.content.queued",
    severity: "warning",
    icon: "clock",
    badgeVariant: "secondary",
  },
  PROCESSING: {
    labelKey: "custom.content.status.processing",
    descriptionKey: "custom.status_presentations.content.processing",
    severity: "info",
    icon: "loader",
    badgeVariant: "secondary",
  },
  RETRYING: {
    labelKey: "custom.content.status.retrying",
    descriptionKey: "custom.status_presentations.content.retrying",
    severity: "warning",
    icon: "refresh",
    badgeVariant: "secondary",
  },
  COMPLETED: {
    labelKey: "custom.content.status.completed",
    descriptionKey: "custom.status_presentations.content.completed",
    severity: "success",
    icon: "check",
    badgeVariant: "secondary",
  },
  FAILED: {
    labelKey: "custom.content.status.failed",
    descriptionKey: "custom.status_presentations.content.failed",
    actionKey: "custom.status_presentations.content.failed_action",
    severity: "error",
    icon: "alert",
    badgeVariant: "destructive",
  },
  REVOKED: {
    labelKey: "custom.content.status.revoked",
    descriptionKey: "custom.status_presentations.content.revoked",
    severity: "neutral",
    icon: "alert",
    badgeVariant: "outline",
  },
};

const KNOWN_PROCESSING_STAGES = new Set([
  "downloading",
  "converting",
  "extracting_images",
  "chunking",
  "embedding",
  "classifying",
  "extracting",
  "indexing",
]);

/**
 * Localize a worker processing stage key. Falls back to the raw key for any
 * unknown stage so newly added worker stages still render before the frontend
 * ships a matching label.
 */
export function stageLabel(
  stage: string | null | undefined,
  translate: (key: string, options?: unknown) => string,
): string | null {
  if (!stage) {
    return null;
  }
  if (KNOWN_PROCESSING_STAGES.has(stage)) {
    return translate(`custom.status_presentations.stages.${stage}`);
  }
  return stage;
}

const REVIEW_REASON_ACTIONS: Record<ContentEnrichmentReviewReason, string> = {
  missing_required_fields: "custom.status_presentations.review.missing_required_fields_action",
  conflicted_fields: "custom.status_presentations.review.conflicted_fields_action",
  missing_evidence: "custom.status_presentations.review.missing_evidence_action",
};

export function contentStatusPresentation(status: ContentItemInfo["status"]): StatusPresentation {
  return (
    (status ? CONTENT_STATUS_PRESENTATIONS[status] : undefined) ?? {
      labelKey: "custom.status_presentations.content.not_processed_label",
      descriptionKey: "custom.status_presentations.content.not_processed",
      actionKey: "custom.content.actions.process",
      severity: "neutral",
      icon: "inbox",
      badgeVariant: "outline",
    }
  );
}

export function reviewStatePresentation(file: ContentItemInfo): ReviewStatePresentation {
  const reasons = getContentEnrichmentReviewReasons(
    file.document_classification,
    file.document_extraction,
  );
  const reviewState = getContentReviewState(file);
  const needsReview =
    file.document_classification?.needs_review === true ||
    hasNeedsReviewContentEnrichment(file.document_extraction) ||
    reasons.length > 0;

  if (reviewState === "stale") {
    return {
      status: "stale",
      reasons,
      labelKey: "custom.content.details.stale_refresh_short",
      descriptionKey: "custom.status_presentations.review.stale",
      actionKey: "custom.content.actions.rerun_enrichment",
      severity: "warning",
      icon: "refresh",
      badgeVariant: "secondary",
    };
  }
  if (reviewState === "needs_review") {
    const firstReason = reasons[0];
    return {
      status: "needs_review",
      reasons,
      labelKey: needsReview
        ? "custom.content.details.needs_attention"
        : "custom.content.details.review_unreviewed",
      descriptionKey: firstReason
        ? `custom.status_presentations.review.${firstReason}`
        : "custom.status_presentations.review.unreviewed",
      actionKey: firstReason
        ? REVIEW_REASON_ACTIONS[firstReason]
        : "custom.content.details.accept_review",
      severity: "warning",
      icon: "alert",
      badgeVariant: "secondary",
    };
  }
  if (reviewState === "reviewed") {
    const detailedStatus = getContentEnrichmentReviewStatus(
      file.document_classification,
      file.document_extraction,
    );
    return {
      status: "reviewed",
      reasons,
      labelKey: "custom.content.details.reviewed",
      descriptionKey:
        detailedStatus === "corrected"
          ? "custom.status_presentations.review.corrected"
          : "custom.status_presentations.review.accepted",
      severity: "success",
      icon: "check",
      badgeVariant: "default",
    };
  }
  return {
    status: "none",
    reasons,
    labelKey: "custom.content.details.no_attention_needed",
    descriptionKey: "custom.content.details.no_attention_needed_description",
    severity: "neutral",
    icon: "check",
    badgeVariant: "outline",
  };
}

export function itemFlowPresentation(file: ContentItemInfo): StatusPresentation {
  const processing = contentStatusPresentation(file.status);
  if (file.status && file.status !== "COMPLETED") {
    return processing;
  }
  const review = reviewStatePresentation(file);
  if (review.status !== "none") {
    return review;
  }
  return processing;
}
