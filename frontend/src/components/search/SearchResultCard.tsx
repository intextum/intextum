import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslate } from "@/lib/app-context";
import { ChevronDown, FileText, Mail, Paperclip } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SearchResult } from "@/dataProvider";
import { buildHighlightedTextSegments, combineSearchResults } from "@/lib/search-results";

interface SearchResultCardProps {
  result: SearchResult;
  matches?: SearchResult[];
  query?: string;
  rank: number;
  onClick?: (result: SearchResult) => void;
}

function HighlightedSnippet({ text, query }: { text: string; query?: string }) {
  return (
    <>
      {buildHighlightedTextSegments(text, query ?? "").map((segment, index) =>
        segment.highlighted ? (
          <mark
            key={`${segment.text}-${index}`}
            className="rounded-sm bg-yellow-200/70 px-0.5 text-foreground dark:bg-yellow-500/30"
          >
            {segment.text}
          </mark>
        ) : (
          <span key={`${segment.text}-${index}`}>{segment.text}</span>
        ),
      )}
    </>
  );
}

export const SearchResultCard = ({
  result,
  matches,
  query,
  rank,
  onClick,
}: SearchResultCardProps) => {
  const translate = useTranslate();
  const [matchesOpen, setMatchesOpen] = useState(false);
  const groupedMatches = matches && matches.length > 0 ? matches : [result];
  const allMatches = [result, ...groupedMatches.filter((match) => match !== result)];
  const combinedResult = allMatches.length > 1 ? combineSearchResults(allMatches) : result;
  const fallbackName = result.file_path.split("/").pop() || result.file_path;
  const title = result.display_name || fallbackName;
  const dirPath = result.file_path.split("/").slice(0, -1).join("/");
  const scorePercent = (combinedResult.score * 100).toFixed(0);
  const sentAtLabel = result.email_sent_at
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(result.email_sent_at))
    : null;
  const KindIcon =
    result.content_kind === "email_message"
      ? Mail
      : result.content_kind === "attachment"
        ? Paperclip
        : FileText;
  const kindLabel =
    result.content_kind === "email_message"
      ? translate("custom.content.search.kind_email_message")
      : result.content_kind === "attachment"
        ? translate("custom.content.search.kind_attachment")
        : translate("custom.content.search.kind_file");
  const kindSpecificMeta =
    result.content_kind === "email_message"
      ? [
          result.email_from_address
            ? translate("custom.content.search.email_from", {
                address: result.email_from_address,
              })
            : null,
          sentAtLabel
            ? translate("custom.content.search.email_sent_at", {
                date: sentAtLabel,
              })
            : null,
        ]
          .filter((value): value is string => Boolean(value))
          .join(" · ")
      : result.content_kind === "attachment" && result.parent_display_name
        ? translate("custom.content.search.attachment_parent", {
            name: result.parent_display_name,
          })
        : null;
  const hiddenMatches = allMatches.slice(1).filter((match) => match.text);

  return (
    <Card
      className="group cursor-pointer transition-all duration-200 hover:border-foreground/20 hover:shadow-md"
      onClick={() => onClick?.(combinedResult)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium text-muted-foreground">
              {rank}
            </div>
            <div className="min-w-0 flex-1">
              <CardTitle className="text-base truncate">{title}</CardTitle>
              {kindSpecificMeta && (
                <CardDescription className="truncate text-xs">{kindSpecificMeta}</CardDescription>
              )}
              {dirPath && (
                <CardDescription className="truncate font-mono text-[10px]">
                  {dirPath}
                </CardDescription>
              )}
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="secondary"
                  className="border-transparent bg-muted/50 font-mono text-muted-foreground"
                >
                  {scorePercent}%
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>
                  {translate("custom.content.search.relevance_score", {
                    score: combinedResult.score.toFixed(4),
                  })}
                </p>
              </TooltipContent>
            </Tooltip>
            {allMatches.length > 1 ? (
              <Badge variant="outline" className="text-xs">
                {translate("custom.content.search.matches", { count: allMatches.length })}
              </Badge>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        {result.text && (
          <p className="mb-3 line-clamp-3 text-sm text-muted-foreground">
            <HighlightedSnippet text={result.text} query={query} />
          </p>
        )}

        {hiddenMatches.length > 0 ? (
          <Collapsible open={matchesOpen} onOpenChange={setMatchesOpen} className="mb-3">
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                onClick={(event) => event.stopPropagation()}
              >
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform ${matchesOpen ? "rotate-180" : ""}`}
                />
                {matchesOpen
                  ? translate("custom.content.search.hide_matches")
                  : translate("custom.content.search.show_more_matches", {
                      count: hiddenMatches.length,
                      plural: hiddenMatches.length === 1 ? "" : "es",
                    })}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent
              className="mt-2 space-y-2"
              onClick={(event) => event.stopPropagation()}
            >
              {hiddenMatches.map((match, index) => (
                <button
                  key={`${match.file_path}-${match.chunk_index}-${index}`}
                  type="button"
                  className="block w-full rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted/60"
                  onClick={() => onClick?.(match)}
                >
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    {translate("custom.content.search.match_label", { index: index + 2 })}
                  </span>
                  <span className="line-clamp-2 text-sm text-muted-foreground">
                    <HighlightedSnippet text={match.text ?? ""} query={query} />
                  </span>
                </button>
              ))}
            </CollapsibleContent>
          </Collapsible>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="text-xs">
            <KindIcon className="mr-1 h-3 w-3" />
            {kindLabel}
          </Badge>
          {combinedResult.page_numbers.length > 0 && (
            <Badge variant="outline" className="text-xs">
              {translate("custom.content.search.pages", {
                plural: combinedResult.page_numbers.length > 1 ? "s" : "",
                pages: combinedResult.page_numbers.join(", "),
              })}
            </Badge>
          )}
          {combinedResult.headings.length > 0 && (
            <Badge variant="outline" className="max-w-[200px] truncate text-xs">
              {combinedResult.headings[0]}
            </Badge>
          )}
          {allMatches.length === 1 && result.chunk_index > 0 && (
            <Badge variant="outline" className="text-xs">
              {translate("custom.content.search.chunk", { index: result.chunk_index })}
            </Badge>
          )}
          {combinedResult.images && combinedResult.images.length > 0 && (
            <Badge variant="outline" className="text-xs">
              {translate("custom.content.search.images", {
                count: combinedResult.images.length,
                plural: combinedResult.images.length > 1 ? "s" : "",
              })}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
