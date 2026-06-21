import type { ContentItemKind } from "./content.ts";

export interface ResearchReportSource {
  file_path: string;
  content_item_id?: string | null;
  display_name?: string | null;
  content_kind?: ContentItemKind | null;
  email_from_address?: string | null;
  email_sent_at?: string | null;
  parent_display_name?: string | null;
  title?: string | null;
  source_kind?: "reviewed_enrichment" | null;
  page_numbers: number[];
  doc_refs: string[];
  citation_index?: number | null;
  images: string[];
  quote?: string | null;
}

export interface ResearchReportImage {
  url: string;
  title?: string | null;
  citation_index?: number | null;
}

export interface ResearchReportSection {
  heading: string;
  body: string;
}

export interface ResearchVerification {
  issues: string[];
}

export interface ResearchRun {
  id: string;
  report_id: string;
  user_sub: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  claimed_by?: string | null;
  claimed_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  last_event_id?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchReportSummary {
  id: string;
  title: string | null;
  prompt: string;
  status: ResearchRun["status"];
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
}

export interface ResearchReportDetail {
  id: string;
  title: string | null;
  prompt: string;
  status: ResearchRun["status"];
  context_file_paths: string[];
  outline: string[];
  sections: ResearchReportSection[];
  sources: ResearchReportSource[];
  images: ResearchReportImage[];
  verification: ResearchVerification;
  content_markdown?: string | null;
  error_message?: string | null;
  run_id?: string | null;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
}

export interface ResearchReportMessageMetadata extends ResearchReportDetail {
  kind: "research_report";
  report_id: string;
  conversation_id: string;
}
