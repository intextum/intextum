import type { AnchorHTMLAttributes } from "react";
import { useMemo } from "react";
import type { ExtraProps } from "streamdown";
import { MessageResponse } from "@/components/ai-elements/message";
import { sourceDisplayTitle } from "@/lib/chat-source-previews";

export interface CitationSource {
  file_path: string;
  content_item_id?: string | null;
  display_name?: string | null;
  content_kind?: "file" | "folder" | "email_message" | "attachment" | null;
  title?: string;
  source_kind?: "reviewed_enrichment" | null;
  page_numbers?: number[];
  doc_refs?: string[];
  citation_index?: number;
  images?: string[];
  quote?: string;
}

interface CitationTextProps {
  text: string;
  sources: CitationSource[];
  onSourceClick: (filePath: string, docRefs?: string[]) => void;
}

const CITATION_PATTERN = /\[(\d+)\]/g;
const CITE_PREFIX = "#cite-";

/**
 * Replace matched citation markers `[N]` with markdown links `[[N]](#cite-N)`
 * that survive markdown parsing. The `a` component override intercepts these
 * and renders citation buttons.
 */
function replaceCitations(
  text: string,
  sourceByCitation: Map<number, CitationSource>,
): { replaced: string; hasLinkedCitation: boolean } {
  let hasLinkedCitation = false;

  const replaced = text.replace(CITATION_PATTERN, (raw, indexText) => {
    const citationIndex = Number(indexText);
    if (!sourceByCitation.has(citationIndex)) return raw;
    hasLinkedCitation = true;
    // Markdown link with fragment href — always passes URL sanitization
    return `[\\[${citationIndex}\\]](${CITE_PREFIX}${citationIndex})`;
  });

  return { replaced, hasLinkedCitation };
}

export const CitationText = ({ text, sources, onSourceClick }: CitationTextProps) => {
  const sourceByCitation = useMemo(() => {
    const map = new Map<number, CitationSource>();
    for (const source of sources) {
      if (typeof source.citation_index === "number" && !map.has(source.citation_index)) {
        map.set(source.citation_index, source);
      }
    }
    return map;
  }, [sources]);

  const { replaced, hasLinkedCitation } = useMemo(
    () => replaceCitations(text, sourceByCitation),
    [text, sourceByCitation],
  );

  const components = useMemo(() => {
    if (!hasLinkedCitation) return undefined;
    return {
      a: (props: AnchorHTMLAttributes<HTMLAnchorElement> & ExtraProps) => {
        const href = props.href ?? "";
        if (!href.startsWith(CITE_PREFIX)) {
          // Regular link — render normally
          return <a {...props} />;
        }
        const citationIndex = Number(href.slice(CITE_PREFIX.length));
        const source = sourceByCitation.get(citationIndex);
        if (!source || Number.isNaN(citationIndex)) {
          return <>{props.children}</>;
        }
        return (
          <button
            type="button"
            className="mx-0.5 inline-flex rounded bg-muted px-1 py-0 text-xs font-medium text-primary hover:bg-muted/70"
            onClick={() => onSourceClick(source.file_path, source.doc_refs)}
            title={sourceDisplayTitle(source)}
          >
            {props.children}
          </button>
        );
      },
    };
  }, [hasLinkedCitation, sourceByCitation, onSourceClick]);

  if (!hasLinkedCitation) {
    return <MessageResponse>{text}</MessageResponse>;
  }

  return <MessageResponse components={components}>{replaced}</MessageResponse>;
};
