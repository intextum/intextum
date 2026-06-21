import { useState, useEffect, useRef, useMemo } from "react";
import { useTranslate } from "@/lib/app-context";
import { Music, Play, Clock, AlertCircle } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { contentApi } from "@/dataProvider";
import { reportClientError } from "@/lib/report-client-error";

interface AudioTranscriptPreviewProps {
  filePath: string;
  previewUrl: string;
}

interface TranscriptSegment {
  text: string;
  startTime: number;
  endTime: number;
  voice?: string;
  timed: boolean;
}

interface TranscriptTimingSource {
  start_time?: number | string;
  end_time?: number | string;
  voice?: string;
  speaker?: string;
}

interface TranscriptTextNode {
  text?: string;
  orig?: string;
  source?: TranscriptTimingSource[] | unknown;
  prov?: TranscriptTimingSource[] | unknown;
}

interface TranscriptDocument {
  texts?: TranscriptTextNode[];
}

const findActiveSegmentIndex = (segments: TranscriptSegment[], time: number) => {
  if (!segments.length) return -1;

  const matchingIndex = segments.findIndex(
    (segment) => time >= segment.startTime && time < segment.endTime,
  );
  if (matchingIndex !== -1) return matchingIndex;

  // Fallback for tiny timing gaps between segments.
  let index = -1;
  for (let i = 0; i < segments.length; i++) {
    if (time >= segments[i].startTime) {
      index = i;
    } else {
      break;
    }
  }
  return index;
};

export const AudioTranscriptPreview = ({ filePath, previewUrl }: AudioTranscriptPreviewProps) => {
  const translate = useTranslate();
  const [docData, setDocData] = useState<TranscriptDocument | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const audioRef = useRef<HTMLAudioElement>(null);
  const activeSegmentRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const loading = loadedPath !== filePath;
  const visibleError = loadedPath === filePath ? error : null;

  // Load transcript data
  useEffect(() => {
    let cancelled = false;

    contentApi
      .getExtractedDocument(filePath)
      .then((data) => {
        if (cancelled) {
          return;
        }
        if (!data) throw new Error("No data received");
        setDocData(data as TranscriptDocument);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        reportClientError(err, undefined, { routeName: "preview:audio-transcript" });
        setDocData(null);
        setError(err instanceof Error ? err.message : "Failed to load transcript");
      })
      .finally(() => {
        if (!cancelled) {
          setLoadedPath(filePath);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [filePath]);

  // Parse and memoize segments
  const segments = useMemo((): TranscriptSegment[] => {
    const result: TranscriptSegment[] = [];
    if (!docData?.texts || !Array.isArray(docData.texts)) return result;

    docData.texts.forEach((node) => {
      if (!node || typeof node !== "object") return;
      const text = node.text || node.orig;
      if (!text) return;

      const sources = Array.isArray(node.source) ? node.source : [];
      const provisions = Array.isArray(node.prov) ? node.prov : [];

      const timeSource =
        sources.find((s) => s && s.start_time !== undefined) ||
        provisions.find((p) => p && p.start_time !== undefined);

      if (timeSource) {
        const startTime = Number(timeSource.start_time);
        const endTime = Number(timeSource.end_time);
        result.push({
          text: text,
          startTime: Number.isFinite(startTime) ? startTime : 0,
          endTime: Number.isFinite(endTime) ? endTime : Number.POSITIVE_INFINITY,
          voice: timeSource.voice || timeSource.speaker,
          timed: Number.isFinite(startTime) && Number.isFinite(endTime),
        });
        return;
      }

      result.push({
        text,
        startTime: 0,
        endTime: Number.POSITIVE_INFINITY,
        timed: false,
      });
    });

    return result.sort((a, b) => a.startTime - b.startTime);
  }, [docData]);

  // Calculate current active index directly from currentTime
  const activeIndex = useMemo(() => {
    return findActiveSegmentIndex(segments, currentTime);
  }, [currentTime, segments]);

  const handleAudioTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);
  };

  const handleAudioDurationChange = () => {
    if (!audioRef.current) return;
    setDuration(Number.isFinite(audioRef.current.duration) ? audioRef.current.duration : 0);
  };

  // Auto-scroll logic when active segment changes
  useEffect(() => {
    if (activeIndex === -1 || !activeSegmentRef.current || !scrollAreaRef.current) return;

    const viewport = scrollAreaRef.current.querySelector(
      "[data-radix-scroll-area-viewport]",
    ) as HTMLDivElement | null;
    if (!viewport) return;

    const activeEl = activeSegmentRef.current;
    const targetTop = activeEl.offsetTop - viewport.clientHeight / 2 + activeEl.clientHeight / 2;
    viewport.scrollTo({
      top: Math.max(0, targetTop),
      behavior: "smooth",
    });
  }, [activeIndex]);

  const formatTime = (seconds: number) => {
    if (isNaN(seconds)) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const handleSegmentClick = (startTime: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = startTime;
      setCurrentTime(startTime);
      audioRef.current.play().catch(() => {});
    }
  };

  if (loading)
    return (
      <div className="h-full w-full p-8 space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-12 w-3/4 rounded-lg" />
        <Skeleton className="h-12 w-full rounded-lg" />
        <Skeleton className="h-12 w-5/6 rounded-lg" />
      </div>
    );

  if (visibleError)
    return (
      <div className="h-full w-full flex flex-col items-center justify-center text-muted-foreground p-8">
        <AlertCircle className="h-12 w-12 opacity-20 mb-4" />
        <p className="text-sm font-medium">{translate("custom.content.preview.not_available")}</p>
        <p className="text-xs opacity-60 mt-1">{visibleError}</p>
      </div>
    );

  return (
    <div className="absolute inset-0 flex flex-col bg-background overflow-hidden">
      {/* Player Header */}
      <div className="p-6 border-b bg-muted/30 shrink-0">
        <div className="max-w-3xl mx-auto flex flex-col gap-4">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <Music className="h-6 w-6 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold truncate text-sm">{filePath.split("/").pop()}</h3>
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-1">
                <Clock className="h-3 w-3" />
                <span className="font-mono">{formatTime(currentTime)}</span>
                <span className="opacity-40">/</span>
                <span className="font-mono">{formatTime(duration)}</span>
              </div>
            </div>
          </div>

          <audio
            ref={audioRef}
            src={previewUrl}
            className="w-full h-10"
            onTimeUpdate={handleAudioTimeUpdate}
            onDurationChange={handleAudioDurationChange}
            onLoadedMetadata={handleAudioDurationChange}
            onSeeking={handleAudioTimeUpdate}
            onSeeked={handleAudioTimeUpdate}
            controls
          />
        </div>
      </div>

      {/* Transcript Area */}
      <div className="flex-1 min-h-0 relative bg-background/50">
        {segments.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2 p-8 text-center">
            <Play className="h-10 w-10 opacity-10 mb-2" />
            <p className="text-sm">{translate("custom.content.preview.no_text")}</p>
            <p className="text-xs opacity-60 max-w-[250px]">
              The file was processed but no timed segments were found in the extraction.
            </p>
          </div>
        ) : (
          <ScrollArea ref={scrollAreaRef} className="h-full">
            <div className="max-w-3xl mx-auto p-8 space-y-2">
              <div className="flex items-center gap-3 mb-8">
                <Badge
                  variant="outline"
                  className="px-3 py-1 bg-background shadow-sm text-[10px] uppercase tracking-wider font-bold"
                >
                  {translate("custom.content.preview.transcript")}
                </Badge>
                <div className="h-px flex-1 bg-border/60" />
              </div>

              {segments.map((segment, idx) => {
                const isActive = idx === activeIndex;
                return (
                  <div
                    key={idx}
                    ref={isActive ? activeSegmentRef : null}
                    onClick={() => {
                      if (segment.timed) handleSegmentClick(segment.startTime);
                    }}
                    className={`group relative flex gap-6 p-4 rounded-xl transition-all cursor-pointer border ${
                      isActive
                        ? "bg-primary/10 border-primary/20 shadow-md scale-[1.01] z-10"
                        : "hover:bg-muted/40 border-transparent"
                    } ${segment.timed ? "cursor-pointer" : "cursor-text"}`}
                  >
                    <div
                      className={`w-12 shrink-0 font-mono text-[10px] mt-1 transition-colors text-right ${
                        isActive ? "text-primary font-bold" : "text-muted-foreground/60"
                      }`}
                    >
                      {segment.timed ? formatTime(segment.startTime) : "Text"}
                    </div>

                    <div className="flex-1 space-y-1">
                      {segment.voice && (
                        <div
                          className={`text-[9px] font-bold uppercase tracking-widest mb-1 transition-colors ${
                            isActive ? "text-primary" : "text-muted-foreground/40"
                          }`}
                        >
                          {segment.voice}
                        </div>
                      )}
                      <p
                        className={`text-sm leading-relaxed transition-colors ${
                          isActive
                            ? "text-foreground font-semibold"
                            : "text-muted-foreground group-hover:text-foreground"
                        }`}
                      >
                        {segment.text}
                      </p>
                    </div>

                    {isActive && (
                      <div className="absolute left-0 top-2 bottom-2 w-1.5 bg-primary rounded-r-full" />
                    )}
                  </div>
                );
              })}

              <div className="h-32" />
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
};
