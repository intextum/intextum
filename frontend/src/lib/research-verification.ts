export type ResearchVerificationSeverity = "critical" | "warning";
export type ResearchVerificationLevel = "healthy" | "warning" | "critical";
export interface ResearchVerificationSourceLike {
  file_path: string;
  content_item_id?: string | null;
  display_name?: string | null;
  content_kind?: "file" | "folder" | "email_message" | "attachment" | null;
  title?: string | null;
  source_kind?: "reviewed_enrichment" | null;
  doc_refs?: string[];
  citation_index?: number | null;
}

export interface ResearchVerificationIssue {
  raw: string;
  message: string;
  section: string | null;
  sectionAnchorId: string | null;
  citationIndices: number[];
  severity: ResearchVerificationSeverity;
}

export interface ResearchVerificationSummary {
  level: ResearchVerificationLevel;
  issueCount: number;
  warningCount: number;
  criticalCount: number;
  affectedSections: string[];
  issues: ResearchVerificationIssue[];
}

const CRITICAL_PATTERNS = [
  /invalid citations/i,
  /cites sources outside the section evidence/i,
  /cites sources without assigned section evidence/i,
  /does not cite any retrieved evidence/i,
];

const WARNING_PATTERNS = [/section evidence was retrieved but the draft cites none of it/i];
const NUMBER_PATTERN = /\d+/g;

export const makeResearchSectionAnchorId = (section: string): string => {
  const normalized = section
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `research-section-${normalized || "section"}`;
};

const parseIssue = (raw: string): ResearchVerificationIssue => {
  const separatorIndex = raw.indexOf(": ");
  const section = separatorIndex > 0 ? raw.slice(0, separatorIndex).trim() || null : null;
  const message = separatorIndex > 0 ? raw.slice(separatorIndex + 2).trim() || raw : raw;
  const citationIndices = Array.from(
    new Set(
      (message.match(NUMBER_PATTERN) ?? [])
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0),
    ),
  );

  const severity: ResearchVerificationSeverity = CRITICAL_PATTERNS.some((pattern) =>
    pattern.test(raw),
  )
    ? "critical"
    : WARNING_PATTERNS.some((pattern) => pattern.test(raw))
      ? "warning"
      : "warning";

  return {
    raw,
    message,
    section,
    sectionAnchorId: section ? makeResearchSectionAnchorId(section) : null,
    citationIndices,
    severity,
  };
};

export const summarizeResearchVerification = (rawIssues: string[]): ResearchVerificationSummary => {
  const issues = rawIssues
    .filter((issue): issue is string => typeof issue === "string" && issue.trim().length > 0)
    .map((issue) => parseIssue(issue.trim()));
  const criticalCount = issues.filter((issue) => issue.severity === "critical").length;
  const warningCount = issues.filter((issue) => issue.severity === "warning").length;
  const affectedSections = Array.from(
    new Set(
      issues.map((issue) => issue.section).filter((section): section is string => Boolean(section)),
    ),
  );

  let level: ResearchVerificationLevel = "healthy";
  if (criticalCount > 0) {
    level = "critical";
  } else if (warningCount > 0) {
    level = "warning";
  }

  return {
    level,
    issueCount: issues.length,
    warningCount,
    criticalCount,
    affectedSections,
    issues,
  };
};

export const groupResearchVerificationIssuesBySection = (
  issues: ResearchVerificationIssue[],
): Record<string, ResearchVerificationIssue[]> => {
  const grouped: Record<string, ResearchVerificationIssue[]> = {};
  for (const issue of issues) {
    if (!issue.section) {
      continue;
    }
    grouped[issue.section] = [...(grouped[issue.section] ?? []), issue];
  }
  return grouped;
};

export const relatedResearchSourcesForIssue = (
  issue: ResearchVerificationIssue,
  sources: ResearchVerificationSourceLike[],
): ResearchVerificationSourceLike[] => {
  if (issue.citationIndices.length === 0) {
    return [];
  }

  const sourceByCitation = new Map<number, ResearchVerificationSourceLike>();
  for (const source of sources) {
    if (typeof source.citation_index === "number" && !sourceByCitation.has(source.citation_index)) {
      sourceByCitation.set(source.citation_index, source);
    }
  }

  return issue.citationIndices
    .map((citationIndex) => sourceByCitation.get(citationIndex))
    .filter((source): source is ResearchVerificationSourceLike => Boolean(source));
};
