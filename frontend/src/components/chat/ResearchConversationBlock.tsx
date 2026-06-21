import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownRight,
  Bot,
  FileText,
  Link2,
  LoaderCircle,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Message, MessageContent } from "@/components/ai-elements/message";
import { CitationText } from "@/components/chat/CitationText";
import type { ResearchReportDetail } from "@/dataProvider";
import type { ConversationProgressEvent } from "@/hooks/useConversationRun";
import { buildExportLabels, buildResearchResponseExportDocument } from "@/lib/chat-export";
import {
  isReviewedEnrichmentSource,
  sourceContextLine,
  sourceDisplayTitle,
} from "@/lib/chat-source-previews";
import {
  groupResearchVerificationIssuesBySection,
  makeResearchSectionAnchorId,
  relatedResearchSourcesForIssue,
  summarizeResearchVerification,
} from "@/lib/research-verification";
import { cn } from "@/lib/utils";
import { ResponseExportMenu } from "./ResponseExportMenu";

const SECTION_HIGHLIGHT_DURATION_MS = 2200;

const statusVariant = (
  status: ResearchReportDetail["status"],
): "secondary" | "destructive" | "outline" => {
  switch (status) {
    case "COMPLETED":
      return "secondary";
    case "FAILED":
      return "destructive";
    case "CANCELLED":
      return "outline";
    default:
      return "outline";
  }
};

const verificationAlertClasses = (level: "healthy" | "warning" | "critical") => {
  switch (level) {
    case "healthy":
      return "border-emerald-500/30 bg-emerald-500/5 text-foreground [&>svg]:text-emerald-600 dark:[&>svg]:text-emerald-400";
    case "warning":
      return "border-amber-500/30 bg-amber-500/5 text-foreground [&>svg]:text-amber-600 dark:[&>svg]:text-amber-400";
    case "critical":
    default:
      return "";
  }
};

const verificationBadgeClasses = (hasCriticalIssue: boolean) =>
  hasCriticalIssue
    ? "border-destructive/40 bg-destructive/10 text-destructive"
    : "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";

interface ResearchConversationBlockProps {
  events: ConversationProgressEvent[];
  isLoading: boolean;
  report: ResearchReportDetail | null;
  translate: (key: string, options?: unknown) => string;
  onSourceClick: (filePath: string, docRefs?: string[]) => void | Promise<void>;
}

export const ResearchConversationBlock = ({
  events,
  isLoading,
  report,
  translate,
  onSourceClick,
}: ResearchConversationBlockProps) => {
  const exportLabels = useMemo(() => buildExportLabels(translate), [translate]);
  const exportUrlOptions = useMemo(
    () => ({
      absoluteBaseUrl: typeof window !== "undefined" ? window.location.origin : undefined,
    }),
    [],
  );
  const [highlightedSectionId, setHighlightedSectionId] = useState<string | null>(null);
  const highlightResetTimeoutRef = useRef<number | null>(null);

  const citationSources = useMemo(
    () =>
      report?.sources.map((source) => ({
        ...source,
        title: source.title ?? undefined,
        citation_index: source.citation_index ?? undefined,
        quote: source.quote ?? undefined,
      })) ?? [],
    [report?.sources],
  );

  const verificationSummary = useMemo(
    () => summarizeResearchVerification(report?.verification.issues ?? []),
    [report?.verification.issues],
  );

  const verificationIssuesBySection = useMemo(
    () => groupResearchVerificationIssuesBySection(verificationSummary.issues),
    [verificationSummary.issues],
  );

  const availableSectionAnchors = useMemo(
    () =>
      new Set(
        (report?.sections ?? []).map((section) => makeResearchSectionAnchorId(section.heading)),
      ),
    [report?.sections],
  );

  const exportDocument = useMemo(() => {
    if (!report) {
      return null;
    }
    return buildResearchResponseExportDocument(report, exportLabels, exportUrlOptions);
  }, [exportLabels, exportUrlOptions, report]);

  const visibleTitle = (() => {
    if (report?.title) {
      return report.title;
    }
    if (report?.prompt) {
      return report.prompt.length <= 80 ? report.prompt : `${report.prompt.slice(0, 77)}...`;
    }
    return translate("custom.pages.research.title");
  })();

  const jumpToSection = useCallback((sectionAnchorId: string) => {
    const target = document.getElementById(sectionAnchorId);
    if (!target) {
      return;
    }
    if (highlightResetTimeoutRef.current !== null) {
      window.clearTimeout(highlightResetTimeoutRef.current);
    }
    setHighlightedSectionId(sectionAnchorId);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    highlightResetTimeoutRef.current = window.setTimeout(() => {
      setHighlightedSectionId((current) => (current === sectionAnchorId ? null : current));
      highlightResetTimeoutRef.current = null;
    }, SECTION_HIGHLIGHT_DURATION_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (highlightResetTimeoutRef.current !== null) {
        window.clearTimeout(highlightResetTimeoutRef.current);
      }
    };
  }, []);

  return (
    <Message from="assistant">
      <div className="flex items-start gap-4">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-background shadow-sm">
          <Bot className="size-4" />
        </div>
        <div className="relative min-w-0 flex-1">
          <MessageContent className="space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="truncate text-lg font-semibold tracking-tight">{visibleTitle}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {report?.status
                    ? translate("custom.pages.research.status_label", { status: report.status })
                    : translate("custom.pages.research.status_label", {
                        status: isLoading ? "RUNNING" : "PENDING",
                      })}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {exportDocument ? (
                  <ResponseExportMenu document={exportDocument} translate={translate} />
                ) : null}
                {isLoading ? (
                  <LoaderCircle className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : null}
                {report?.status ? (
                  <Badge variant={statusVariant(report.status)}>{report.status}</Badge>
                ) : null}
              </div>
            </div>

            {events.length > 0 && (
              <section className="space-y-3">
                <h4 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
                  {translate("custom.pages.research.progress")}
                </h4>
                <div className="space-y-2">
                  {events.map((event, index) => (
                    <div key={`${event.event}-${index}`} className="rounded-md border px-3 py-2">
                      <p className="text-sm font-medium">{event.message}</p>
                      {event.phase ? (
                        <p className="text-xs text-muted-foreground">{event.phase}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {report?.error_message ? (
              <section className="rounded-md border border-destructive/40 bg-destructive/5 p-4">
                <p className="text-sm font-medium text-destructive">
                  {translate("custom.pages.research.error_title")}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">{report.error_message}</p>
              </section>
            ) : null}

            {report && (
              <>
                <section className="space-y-3">
                  <Alert
                    variant={verificationSummary.level === "critical" ? "destructive" : "default"}
                    className={verificationAlertClasses(verificationSummary.level)}
                  >
                    {verificationSummary.level === "healthy" ? (
                      <ShieldCheck className="h-4 w-4" />
                    ) : verificationSummary.level === "warning" ? (
                      <ShieldAlert className="h-4 w-4" />
                    ) : (
                      <TriangleAlert className="h-4 w-4" />
                    )}
                    <AlertTitle>
                      {translate(
                        verificationSummary.level === "healthy"
                          ? "custom.pages.research.verification_healthy_title"
                          : verificationSummary.level === "warning"
                            ? "custom.pages.research.verification_warning_title"
                            : "custom.pages.research.verification_critical_title",
                      )}
                    </AlertTitle>
                    <AlertDescription>
                      <p>
                        {translate(
                          verificationSummary.level === "healthy"
                            ? "custom.pages.research.verification_healthy_description"
                            : verificationSummary.level === "warning"
                              ? "custom.pages.research.verification_warning_description"
                              : "custom.pages.research.verification_critical_description",
                          { count: verificationSummary.issueCount },
                        )}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Badge variant="outline">
                          {translate("custom.pages.research.verification_issue_count", {
                            count: verificationSummary.issueCount,
                          })}
                        </Badge>
                        {verificationSummary.criticalCount > 0 ? (
                          <Badge
                            variant="outline"
                            className="border-destructive/40 bg-destructive/10 text-destructive"
                          >
                            {translate("custom.pages.research.verification_critical_count", {
                              count: verificationSummary.criticalCount,
                            })}
                          </Badge>
                        ) : null}
                        {verificationSummary.warningCount > 0 ? (
                          <Badge
                            variant="outline"
                            className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                          >
                            {translate("custom.pages.research.verification_warning_count", {
                              count: verificationSummary.warningCount,
                            })}
                          </Badge>
                        ) : null}
                      </div>
                    </AlertDescription>
                  </Alert>
                </section>

                {report.images.length > 0 && (
                  <section className="space-y-3">
                    <h4 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
                      {translate("custom.pages.research.images")}
                    </h4>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {report.images.map((image) => (
                        <div
                          key={`${image.url}-${image.citation_index ?? "img"}`}
                          className="overflow-hidden rounded-md border"
                        >
                          <img
                            src={image.url}
                            alt={image.title || translate("custom.pages.research.image_alt")}
                            className="aspect-[4/3] w-full object-cover"
                          />
                          <div className="border-t px-3 py-2 text-xs text-muted-foreground">
                            {image.title || translate("custom.pages.research.image_alt")}
                            {typeof image.citation_index === "number"
                              ? ` [${image.citation_index}]`
                              : ""}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                <section className="space-y-6">
                  {report.sections.length === 0 ? (
                    <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                      {translate("custom.pages.research.no_sections")}
                    </div>
                  ) : (
                    report.sections.map((section) => (
                      <article
                        key={section.heading}
                        id={makeResearchSectionAnchorId(section.heading)}
                        className={cn(
                          "scroll-mt-6 space-y-3 rounded-md border border-transparent px-3 py-3 transition-colors duration-500",
                          highlightedSectionId === makeResearchSectionAnchorId(section.heading)
                            ? "border-primary/40 bg-primary/5 shadow-sm"
                            : "",
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <h4 className="text-lg font-semibold">{section.heading}</h4>
                          {(verificationIssuesBySection[section.heading]?.length ?? 0) > 0 ? (
                            <Badge
                              variant="outline"
                              className={verificationBadgeClasses(
                                verificationIssuesBySection[section.heading]?.some(
                                  (issue) => issue.severity === "critical",
                                ) ?? false,
                              )}
                            >
                              <TriangleAlert className="mr-1 h-3 w-3" />
                              {translate("custom.pages.research.verification_section_issue_count", {
                                count: verificationIssuesBySection[section.heading]?.length ?? 0,
                              })}
                            </Badge>
                          ) : null}
                        </div>
                        <CitationText
                          text={section.body}
                          sources={citationSources}
                          onSourceClick={onSourceClick}
                        />
                        <Separator />
                      </article>
                    ))
                  )}
                </section>

                {verificationSummary.issueCount > 0 && (
                  <section className="space-y-3">
                    <h4 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
                      {translate("custom.pages.research.verification_review_items")}
                    </h4>
                    <div className="space-y-2">
                      {verificationSummary.issues.map((issue) => {
                        const relatedSources = relatedResearchSourcesForIssue(
                          issue,
                          report.sources,
                        );
                        const canJumpToSection =
                          issue.sectionAnchorId !== null &&
                          availableSectionAnchors.has(issue.sectionAnchorId);

                        return (
                          <div key={issue.raw} className="rounded-md border px-3 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge
                                variant="outline"
                                className={verificationBadgeClasses(issue.severity === "critical")}
                              >
                                {translate(
                                  issue.severity === "critical"
                                    ? "custom.pages.research.verification_severity_critical"
                                    : "custom.pages.research.verification_severity_warning",
                                )}
                              </Badge>
                              <Badge variant="outline">
                                {issue.section ??
                                  translate("custom.pages.research.verification_report_wide")}
                              </Badge>
                            </div>
                            <p className="mt-2 text-sm text-muted-foreground">{issue.message}</p>
                            {(canJumpToSection || relatedSources.length > 0) && (
                              <div className="mt-3 flex flex-wrap gap-2">
                                {canJumpToSection && issue.sectionAnchorId ? (
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={() => jumpToSection(issue.sectionAnchorId!)}
                                  >
                                    <ArrowDownRight className="h-3.5 w-3.5" />
                                    {translate(
                                      "custom.pages.research.verification_jump_to_section",
                                    )}
                                  </Button>
                                ) : null}
                                {relatedSources.map((source) => (
                                  <Button
                                    key={`${issue.raw}-${source.citation_index ?? source.file_path}`}
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={() =>
                                      void onSourceClick(source.file_path, source.doc_refs)
                                    }
                                  >
                                    <Link2 className="h-3.5 w-3.5" />
                                    {typeof source.citation_index === "number"
                                      ? `[${source.citation_index}] `
                                      : ""}
                                    {sourceDisplayTitle(source)}
                                  </Button>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}

                {report.sources.length > 0 && (
                  <section className="space-y-3">
                    <h4 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
                      {translate("custom.pages.research.sources")}
                    </h4>
                    <div className="space-y-2">
                      {report.sources.map((source) => (
                        <button
                          key={`${source.file_path}-${source.citation_index ?? "src"}`}
                          type="button"
                          onClick={() => void onSourceClick(source.file_path, source.doc_refs)}
                          className="w-full rounded-md border px-3 py-3 text-left hover:bg-muted/30"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-sm font-medium">
                                {typeof source.citation_index === "number"
                                  ? `[${source.citation_index}] `
                                  : ""}
                                {sourceDisplayTitle(source)}
                              </p>
                              <div className="mt-1 flex flex-wrap items-center gap-2">
                                {isReviewedEnrichmentSource(source) && (
                                  <Badge variant="secondary" className="text-[10px]">
                                    {translate(
                                      "custom.pages.chat.tools.source_badge_reviewed_enrichment",
                                    )}
                                  </Badge>
                                )}
                                <p className="truncate text-xs text-muted-foreground">
                                  {source.file_path}
                                </p>
                                {sourceContextLine(source, translate) && (
                                  <p className="truncate text-xs text-muted-foreground">
                                    {sourceContextLine(source, translate)}
                                  </p>
                                )}
                              </div>
                            </div>
                            {source.page_numbers.length > 0 ? (
                              <Badge variant="outline">
                                {translate("custom.pages.research.pages", {
                                  pages: source.page_numbers.join(", "),
                                })}
                              </Badge>
                            ) : null}
                          </div>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}
          </MessageContent>
        </div>
      </div>
    </Message>
  );
};
