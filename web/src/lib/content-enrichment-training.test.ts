import assert from "node:assert/strict";
import test from "node:test";

import {
  buildContentEnrichmentPromotionRefreshPlan,
  buildContentEnrichmentPromotionReviewPath,
  formatContentEnrichmentMetricDuration,
  formatContentEnrichmentMetricNumber,
  formatContentEnrichmentMetricPercent,
  formatContentEnrichmentMetricSize,
  normalizeContentEnrichmentSchemaModels,
  parseContentEnrichmentRegistryModelRef,
  resolveContentEnrichmentCurrentModel,
  resolveContentEnrichmentExtractionModel,
  summarizeContentEnrichmentPromotionImpact,
  summarizeContentEnrichmentTrainingMetrics,
} from "./content-enrichment-training.ts";

test("parseContentEnrichmentRegistryModelRef extracts registry ids", () => {
  assert.equal(parseContentEnrichmentRegistryModelRef("registry:model-1"), "model-1");
  assert.equal(parseContentEnrichmentRegistryModelRef(" registry:model-2 "), "model-2");
  assert.equal(parseContentEnrichmentRegistryModelRef("fastino/gliner2"), null);
  assert.equal(parseContentEnrichmentRegistryModelRef("registry:   "), null);
});

test("resolveContentEnrichmentCurrentModel resolves registry-backed settings", () => {
  const resolved = resolveContentEnrichmentCurrentModel("registry:model-1", [
    {
      id: "model-1",
      target_kind: "classification",
      training_method: "lora",
      status: "ready",
      base_model: "fastino/gliner2-multi-v1",
      target_name: null,
      config_fingerprint: "fp-1",
      reviewed_example_count: 42,
      artifact_path: "content-enrichment/model-1/adapter.tar.gz",
      metrics: { best_metric: 0.91 },
      created_by: "admin",
      is_active: true,
      created_at: "2026-04-26T10:00:00Z",
      updated_at: "2026-04-26T10:10:00Z",
    },
  ]);

  assert.deepEqual(resolved, {
    kind: "registry",
    model: "registry:model-1",
    registry_model_id: "model-1",
    registry_model: {
      id: "model-1",
      target_kind: "classification",
      training_method: "lora",
      status: "ready",
      base_model: "fastino/gliner2-multi-v1",
      target_name: null,
      config_fingerprint: "fp-1",
      reviewed_example_count: 42,
      artifact_path: "content-enrichment/model-1/adapter.tar.gz",
      metrics: { best_metric: 0.91 },
      created_by: "admin",
      is_active: true,
      created_at: "2026-04-26T10:00:00Z",
      updated_at: "2026-04-26T10:10:00Z",
    },
  });

  assert.deepEqual(resolveContentEnrichmentCurrentModel("fastino/gliner2", []), {
    kind: "base",
    model: "fastino/gliner2",
  });
});

test("schema-specific extraction model helpers normalize and resolve scoped adapters", () => {
  assert.deepEqual(
    normalizeContentEnrichmentSchemaModels({
      invoice_fields: " registry:model-2 ",
      " ": "registry:ignored",
      permit_core: 42,
    }),
    {
      invoice_fields: "registry:model-2",
    },
  );

  const resolved = resolveContentEnrichmentExtractionModel(
    "fastino/gliner2",
    "invoice_fields",
    { invoice_fields: "registry:model-2" },
    [
      {
        id: "model-2",
        target_kind: "extraction",
        training_method: "lora",
        status: "ready",
        base_model: "fastino/gliner2-multi-v1",
        target_name: "invoice_fields",
        config_fingerprint: "fp-2",
        reviewed_example_count: 10,
        artifact_path: "content-enrichment/model-2/adapter.tar.gz",
        metrics: null,
        created_by: "admin",
        is_active: true,
        created_at: "2026-04-26T10:00:00Z",
        updated_at: "2026-04-26T10:10:00Z",
      },
    ],
  );

  assert.equal(resolved?.kind, "registry");
  assert.equal(resolved?.registry_model_id, "model-2");
});

test("summarizeContentEnrichmentTrainingMetrics normalizes numeric metrics", () => {
  assert.deepEqual(
    summarizeContentEnrichmentTrainingMetrics({
      best_metric: 0.913,
      train_loss: 0.12,
      eval_loss: 0.09,
      training_duration_seconds: 31.4,
      artifact_size_bytes: 2048,
      global_step: 18,
      epochs_completed: 3,
      train_example_count: 99,
      validation_example_count: 11,
      validation_accuracy: 0.82,
      validation_exact_match_rate: 0.71,
      validation_field_accuracy: 0.93,
      validation_status: "completed",
      validation_error: "unused",
      ignored: "value",
    }),
    {
      best_metric: 0.913,
      train_loss: 0.12,
      eval_loss: 0.09,
      training_duration_seconds: 31.4,
      artifact_size_bytes: 2048,
      global_step: 18,
      epochs_completed: 3,
      train_example_count: 99,
      validation_example_count: 11,
      validation_accuracy: 0.82,
      validation_exact_match_rate: 0.71,
      validation_field_accuracy: 0.93,
      validation_status: "completed",
      validation_error: "unused",
    },
  );
});

test("content enrichment metric formatters keep values readable", () => {
  assert.equal(formatContentEnrichmentMetricNumber(0.9134), "0.913");
  assert.equal(formatContentEnrichmentMetricNumber(14), "14");
  assert.equal(formatContentEnrichmentMetricPercent(0.82), "82%");
  assert.equal(formatContentEnrichmentMetricPercent(0.034), "3.4%");
  assert.equal(formatContentEnrichmentMetricDuration(9.4), "9.4s");
  assert.equal(formatContentEnrichmentMetricDuration(74), "1m 14s");
  assert.equal(formatContentEnrichmentMetricSize(0), "0 B");
  assert.equal(formatContentEnrichmentMetricSize(1536), "1.5 KB");
});

test("promotion impact helpers build stale review paths and deltas", () => {
  assert.equal(
    buildContentEnrichmentPromotionReviewPath("classification", null),
    "/content?stale_enrichment=true",
  );
  assert.equal(
    buildContentEnrichmentPromotionReviewPath("extraction", "permit_core"),
    "/content?stale_enrichment=true&extraction_schema=permit_core",
  );

  assert.deepEqual(
    summarizeContentEnrichmentPromotionImpact({
      staleFileCount: 9,
      newlyStaleFileCount: 5,
      targetKind: "extraction",
      targetName: "permit_core",
    }),
    {
      stale_count: 9,
      stale_increase: 5,
      review_path: "/content?stale_enrichment=true&extraction_schema=permit_core",
      target_kind: "extraction",
      target_name: "permit_core",
    },
  );
});

test("promotion refresh plan helpers scope stale reruns to the promoted target", () => {
  assert.deepEqual(buildContentEnrichmentPromotionRefreshPlan("classification", null), {
    filters: { stale_enrichment: true },
  });
  assert.deepEqual(buildContentEnrichmentPromotionRefreshPlan("extraction", "permit_core"), {
    filters: { stale_enrichment: true, extraction_schema: "permit_core" },
  });
});
