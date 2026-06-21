export const normalizeAuditLabelKey = (value: string): string => value.trim().toLowerCase();

export const auditStatusLabels: Record<string, string> = {
  cancelled: "Dismissed",
  claimed: "Claimed",
  completed: "Completed",
  failed: "Failed",
  pending: "Pending",
  processing: "Processing",
  queued: "Queued",
  ready: "Ready",
  retrying: "Retrying",
  revoked: "Revoked",
  running: "Running",
  skipped: "Skipped",
  suggested: "Suggested",
  superseded: "Superseded",
  training: "Training",
};

export const auditGroupLabels: Record<string, string> = {
  content: "Content",
  enrichment: "Enrichment",
  processing: "Processing",
  review: "Review",
};
