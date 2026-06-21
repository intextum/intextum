import assert from "node:assert/strict";
import test from "node:test";

import {
  applyClassSettingsImport,
  applyClassificationSettingsImport,
  applyExtractionSettingsImport,
  buildClassSettingsExport,
  buildClassificationSettingsExport,
  buildExtractionSettingsExport,
  cloneDocumentClassDraft,
  createEmptyDocumentClassDraft,
  createEmptyExtractionFieldDraft,
  createEmptyExtractionSchemaDraft,
  removeDocumentClassDraft,
  replaceDocumentClassDraft,
  serializeDocumentClassDrafts,
  summarizeContentEnrichmentQueue,
  summarizeContentEnrichmentRerun,
  toDocumentClassDrafts,
  validateContentEnrichmentDrafts,
} from "./content-enrichment-admin.ts";

test("document class drafts round-trip nested extraction schemas", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      version: 7,
      description: "Billing document",
      aliases: ["Rechnung", "Invoice form"],
      extraction_schema: {
        id: "schema-invoice-fields",
        name: "invoice_fields",
        version: 3,
        description: "Extract invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
            required: true,
            fields: [],
            examples: [
              {
                text: "Invoice No. 4711",
                value: "4711",
              },
            ],
          },
        ],
      },
    },
  ]);

  assert.equal(drafts[0]?.id, "class-invoice");
  assert.equal(drafts[0]?.version, 7);
  assert.equal(drafts[0]?.aliases_text, "Rechnung, Invoice form");
  assert.equal(drafts[0]?.extraction_schema?.version, 3);

  assert.deepEqual(serializeDocumentClassDrafts(drafts), [
    {
      id: "class-invoice",
      name: "Invoice",
      description: "Billing document",
      aliases: ["Rechnung", "Invoice form"],
      extraction_schema: {
        id: "schema-invoice-fields",
        name: "invoice_fields",
        description: "Extract invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
            required: true,
            fields: [],
            examples: [
              {
                text: "Invoice No. 4711",
                value: "4711",
              },
            ],
          },
        ],
      },
    },
  ]);
});

test("document class draft helpers clone nested schema editing state", () => {
  const original = toDocumentClassDrafts([
    {
      id: "class-permit",
      name: "Permit",
      version: 2,
      description: "Permit document",
      aliases: ["Notice"],
      extraction_schema: {
        id: "schema-permit",
        name: "permit_fields",
        version: 4,
        description: "Permit fields",
        fields: [
          {
            name: "conditions",
            dtype: "object_list",
            description: "Conditions",
            required: true,
            fields: [{ name: "title", dtype: "str", description: "Title", required: true }],
            examples: [
              {
                text: "Condition A",
                value: { title: "Condition A" },
                child_values: { title: "Condition A" },
                extraction_text: "Condition A",
              },
            ],
          },
        ],
        scenes: [
          {
            text: "Condition A applies",
            extractions: [
              {
                field: "conditions",
                extraction_text: "Condition A",
                value: { title: "Condition A" },
                child_values: { title: "Condition A" },
              },
            ],
          },
        ],
      },
    },
  ])[0]!;

  const cloned = cloneDocumentClassDraft(original);
  cloned.extraction_schema!.fields[0]!.fields[0]!.name = "changed";
  cloned.extraction_schema!.fields[0]!.examples[0]!.child_values.title = "Changed";
  cloned.extraction_schema!.scenes[0]!.extractions[0]!.child_values.title = "Scene changed";

  assert.equal(original.extraction_schema!.fields[0]!.fields[0]!.name, "title");
  assert.equal(
    original.extraction_schema!.fields[0]!.examples[0]!.child_values.title,
    "Condition A",
  );
  assert.equal(
    original.extraction_schema!.scenes[0]!.extractions[0]!.child_values.title,
    "Condition A",
  );
});

test("document class draft list helpers replace, append, and remove classes immutably", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      description: "Billing document",
      aliases: [],
      extraction_schema: null,
    },
    {
      id: "class-permit",
      name: "Permit",
      description: "Permit document",
      aliases: [],
      extraction_schema: null,
    },
  ]);

  const edited = cloneDocumentClassDraft(drafts[0]!);
  edited.name = "Incoming Invoice";
  const replaced = replaceDocumentClassDraft(drafts, 0, edited);
  assert.deepEqual(
    replaced.map((draft) => draft.name),
    ["Incoming Invoice", "Permit"],
  );
  assert.equal(drafts[0]!.name, "Invoice");

  const appended = replaceDocumentClassDraft(drafts, null, edited);
  assert.deepEqual(
    appended.map((draft) => draft.name),
    ["Invoice", "Permit", "Incoming Invoice"],
  );

  const removed = removeDocumentClassDraft(appended, 1);
  assert.deepEqual(
    removed.map((draft) => draft.name),
    ["Invoice", "Incoming Invoice"],
  );
});

test("classification settings export/import only class metadata and preserve identity", () => {
  const draft = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      version: 7,
      description: "Billing document",
      aliases: ["Rechnung"],
      extraction_schema: {
        id: "schema-invoice",
        name: "invoice_fields",
        version: 3,
        description: "Invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
          },
        ],
      },
    },
  ])[0]!;

  assert.deepEqual(buildClassificationSettingsExport(draft), {
    kind: "content_enrichment_classification_settings",
    schema_version: 1,
    classification: {
      name: "Invoice",
      description: "Billing document",
      aliases: ["Rechnung"],
    },
  });

  const imported = applyClassificationSettingsImport(draft, {
    kind: "content_enrichment_classification_settings",
    schema_version: 1,
    classification: {
      name: "Permit",
      description: "Permit document",
      aliases: ["Approval", "Notice"],
    },
  });

  assert.equal(imported.id, "class-invoice");
  assert.equal(imported.version, 7);
  assert.equal(imported.name, "Permit");
  assert.equal(imported.description, "Permit document");
  assert.equal(imported.aliases_text, "Approval, Notice");
  assert.equal(imported.extraction_schema?.id, "schema-invoice");
});

test("extraction settings export/import preserve class metadata and schema identity", () => {
  const draft = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      version: 7,
      description: "Billing document",
      aliases: ["Rechnung"],
      extraction_schema: {
        id: "schema-invoice",
        name: "invoice_fields",
        version: 3,
        description: "Invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
            required: true,
          },
        ],
        scenes: [
          {
            text: "Invoice RE-1",
            extractions: [{ field: "invoice_number", extraction_text: "RE-1", value: "RE-1" }],
          },
        ],
      },
    },
  ])[0]!;

  const exported = buildExtractionSettingsExport(draft);
  assert.equal(exported.kind, "content_enrichment_extraction_settings");
  assert.equal(exported.schema_version, 1);
  assert.equal(exported.extraction.enabled, true);
  assert.deepEqual(exported.extraction.schema, {
    id: "schema-invoice",
    name: "invoice_fields",
    description: "Invoice fields",
    scenes: [
      {
        text: "Invoice RE-1",
        extractions: [{ field: "invoice_number", extraction_text: "RE-1", value: "RE-1" }],
      },
    ],
    fields: [
      {
        name: "invoice_number",
        dtype: "str",
        description: "Invoice number",
        required: true,
        fields: [],
        examples: [],
      },
    ],
  });

  const imported = applyExtractionSettingsImport(draft, {
    kind: "content_enrichment_extraction_settings",
    schema_version: 1,
    extraction: {
      enabled: true,
      schema: {
        name: "permit_fields",
        description: "Permit fields",
        fields: [
          {
            name: "due_date",
            dtype: "date",
            description: "Due date",
            required: false,
            examples: [{ text: "Due 2026-04-29", value: "2026-04-29" }],
          },
        ],
        scenes: [],
      },
    },
  });

  assert.equal(imported.id, "class-invoice");
  assert.equal(imported.name, "Invoice");
  assert.equal(imported.extraction_schema?.id, "schema-invoice");
  assert.equal(imported.extraction_schema?.version, 3);
  assert.equal(imported.extraction_schema?.name, "permit_fields");
  assert.equal(imported.extraction_schema?.fields[0]?.name, "due_date");
});

test("class settings export/import combines classification and extraction", () => {
  const draft = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      version: 7,
      description: "Billing document",
      aliases: ["Rechnung"],
      extraction_schema: {
        id: "schema-invoice",
        name: "invoice_fields",
        version: 3,
        description: "Invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
            required: true,
          },
        ],
      },
    },
  ])[0]!;

  const exported = buildClassSettingsExport(draft);
  assert.deepEqual(exported, {
    kind: "content_enrichment_class_settings",
    schema_version: 1,
    classification: {
      name: "Invoice",
      description: "Billing document",
      aliases: ["Rechnung"],
    },
    extraction: {
      enabled: true,
      schema: {
        name: "invoice_fields",
        description: "Invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
            required: true,
            fields: [],
            examples: [],
          },
        ],
      },
    },
  });

  const importedIntoExisting = applyClassSettingsImport(draft, {
    kind: "content_enrichment_class_settings",
    schema_version: 1,
    classification: {
      name: "Permit",
      description: "Permit document",
      aliases: ["Approval"],
    },
    extraction: {
      enabled: true,
      schema: {
        name: "permit_fields",
        description: "Permit fields",
        fields: [
          {
            name: "due_date",
            dtype: "date",
            description: "Due date",
          },
        ],
      },
    },
  });

  assert.equal(importedIntoExisting.id, "class-invoice");
  assert.equal(importedIntoExisting.version, 7);
  assert.equal(importedIntoExisting.name, "Permit");
  assert.equal(importedIntoExisting.extraction_schema?.id, "schema-invoice");
  assert.equal(importedIntoExisting.extraction_schema?.version, 3);

  const importedAsNewClass = applyClassSettingsImport(createEmptyDocumentClassDraft(), exported);
  assert.ok(importedAsNewClass.id);
  assert.notEqual(importedAsNewClass.id, "class-invoice");
  assert.ok(importedAsNewClass.extraction_schema?.id);
  assert.notEqual(importedAsNewClass.extraction_schema?.id, "schema-invoice");
  assert.equal(importedAsNewClass.name, "Invoice");
});

test("extraction settings import can disable extraction or create a schema id", () => {
  const draft = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      description: "Billing document",
      aliases: [],
      extraction_schema: {
        id: "schema-invoice",
        name: "invoice_fields",
        description: "Invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
          },
        ],
      },
    },
  ])[0]!;

  const disabled = applyExtractionSettingsImport(draft, {
    kind: "content_enrichment_extraction_settings",
    schema_version: 1,
    extraction: { enabled: false, schema: null },
  });
  assert.equal(disabled.extraction_schema, null);

  const recreated = applyExtractionSettingsImport(disabled, {
    kind: "content_enrichment_extraction_settings",
    schema_version: 1,
    extraction: {
      enabled: true,
      schema: {
        name: "invoice_fields",
        description: "Invoice fields",
        fields: [
          {
            name: "invoice_number",
            dtype: "str",
            description: "Invoice number",
          },
        ],
      },
    },
  });
  assert.ok(recreated.extraction_schema?.id);
  assert.notEqual(recreated.extraction_schema?.id, "schema-invoice");
});

test("settings import rejects wrong envelopes and invalid extraction shapes", () => {
  const draft = createEmptyDocumentClassDraft();
  draft.name = "Invoice";

  assert.throws(
    () =>
      applyClassificationSettingsImport(draft, {
        kind: "content_enrichment_extraction_settings",
        schema_version: 1,
      }),
    /invalid_import/,
  );
  assert.throws(
    () =>
      applyExtractionSettingsImport(draft, {
        kind: "content_enrichment_extraction_settings",
        schema_version: 2,
        extraction: { enabled: false, schema: null },
      }),
    /invalid_import/,
  );
  assert.throws(
    () =>
      applyExtractionSettingsImport(draft, {
        kind: "content_enrichment_extraction_settings",
        schema_version: 1,
        extraction: {
          enabled: true,
          schema: {
            name: "invoice_fields",
            description: "Invoice fields",
            fields: [{ name: "amount", dtype: "unknown", description: "Amount" }],
          },
        },
      }),
    /invalid_import/,
  );
  assert.throws(
    () =>
      applyClassSettingsImport(draft, {
        kind: "content_enrichment_class_settings",
        schema_version: 1,
        classification: { name: "Invoice", description: "Invoice", aliases: [] },
        extraction: {
          enabled: true,
          schema: {
            name: "invoice_fields",
            description: "Invoice fields",
            fields: [{ name: "items", dtype: "object_list", description: "Items" }],
          },
        },
      }),
    /invalid_import/,
  );
});

test("document class drafts serialize removed extraction as null", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-invoice",
      name: "Invoice",
      description: "Billing document",
      aliases: [],
      extraction_schema: null,
    },
  ]);

  assert.deepEqual(serializeDocumentClassDrafts(drafts), [
    {
      id: "class-invoice",
      name: "Invoice",
      description: "Billing document",
      aliases: [],
      extraction_schema: null,
    },
  ]);
});

test("document class drafts serialize object-list fields with child fields", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-permit",
      name: "Permit",
      description: "",
      aliases: [],
      extraction_schema: {
        id: "schema-permit-fields",
        name: "permit_fields",
        description: "",
        fields: [
          {
            name: "tasks",
            dtype: "object_list",
            description: "Tasks mentioned in the permit.",
            required: false,
            examples: [
              {
                text: "The applicant must submit monitoring by 2026-04-29.",
                value: {
                  title: "Submit monitoring",
                  due_date: "2026-04-29",
                },
              },
            ],
            fields: [
              {
                name: "title",
                dtype: "str",
                description: "Task title",
                required: true,
              },
              {
                name: "due_date",
                dtype: "date",
                description: "Task due date",
                required: false,
              },
            ],
          },
        ],
      },
    },
  ]);

  assert.deepEqual(serializeDocumentClassDrafts(drafts)[0]?.extraction_schema, {
    id: "schema-permit-fields",
    name: "permit_fields",
    description: "",
    fields: [
      {
        name: "tasks",
        dtype: "object_list",
        description: "Tasks mentioned in the permit.",
        required: false,
        clustered_under_heading: true,
        examples: [
          {
            text: "The applicant must submit monitoring by 2026-04-29.",
            value: {
              title: "Submit monitoring",
              due_date: "2026-04-29",
            },
          },
        ],
        fields: [
          {
            name: "title",
            dtype: "str",
            description: "Task title",
            required: true,
          },
          {
            name: "due_date",
            dtype: "date",
            description: "Task due date",
            required: false,
          },
        ],
      },
    ],
  });
});

test("document class drafts round-trip extraction_text anchors when set", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-permit",
      name: "Permit",
      description: "",
      aliases: [],
      extraction_schema: {
        id: "schema-permit-fields",
        name: "permit_fields",
        description: "",
        fields: [
          {
            name: "due_date",
            dtype: "date",
            description: "Permit due date",
            required: false,
            fields: [],
            examples: [
              {
                text: "Frist: 31.12.2026.",
                value: "2026-12-31",
                extraction_text: "31.12.2026",
              },
            ],
          },
        ],
      },
    },
  ]);

  assert.equal(drafts[0]?.extraction_schema?.fields[0]?.examples[0]?.extraction_text, "31.12.2026");

  const serialized = serializeDocumentClassDrafts(drafts) as Array<{
    extraction_schema: { fields: { examples: Record<string, unknown>[] }[] };
  }>;
  assert.deepEqual(serialized[0].extraction_schema.fields[0].examples, [
    {
      text: "Frist: 31.12.2026.",
      value: "2026-12-31",
      extraction_text: "31.12.2026",
    },
  ]);
});

test("document class drafts omit extraction_text from serialization when empty", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-permit",
      name: "Permit",
      description: "",
      aliases: [],
      extraction_schema: {
        id: "schema-permit-fields",
        name: "permit_fields",
        description: "",
        fields: [
          {
            name: "due_date",
            dtype: "date",
            description: "Permit due date",
            required: false,
            fields: [],
            examples: [
              {
                text: "Frist: 31.12.2026.",
                value: "2026-12-31",
              },
            ],
          },
        ],
      },
    },
  ]);

  const serialized = serializeDocumentClassDrafts(drafts) as Array<{
    extraction_schema: { fields: { examples: Record<string, unknown>[] }[] };
  }>;
  const example = serialized[0].extraction_schema.fields[0].examples[0];
  assert.equal("extraction_text" in example, false);
});

test("document class drafts round-trip scenes with anchored extractions", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-shakespeare",
      name: "Shakespeare",
      description: "",
      aliases: [],
      extraction_schema: {
        id: "schema-literature-fields",
        name: "literature_fields",
        description: "",
        fields: [
          {
            name: "character",
            dtype: "object_list",
            description: "Speaking character",
            required: false,
            fields: [{ name: "name", dtype: "str", description: "Character name", required: true }],
            examples: [],
          },
        ],
        scenes: [
          {
            text: "ROMEO. But soft! What light through yonder window breaks?",
            extractions: [
              {
                field: "character",
                extraction_text: "ROMEO",
                value: { name: "ROMEO" },
              },
            ],
          },
        ],
      },
    },
  ]);

  const schema = drafts[0]?.extraction_schema;
  assert.equal(schema?.scenes.length, 1);
  assert.equal(schema?.scenes[0]?.extractions[0]?.field, "character");
  assert.equal(schema?.scenes[0]?.extractions[0]?.extraction_text, "ROMEO");
  assert.equal(schema?.scenes[0]?.extractions[0]?.child_values.name, "ROMEO");

  const serialized = serializeDocumentClassDrafts(drafts) as Array<{
    extraction_schema: {
      scenes: Array<{
        text: string;
        extractions: Array<{ field: string; extraction_text: string; value: unknown }>;
      }>;
    };
  }>;
  assert.deepEqual(serialized[0].extraction_schema.scenes, [
    {
      text: "ROMEO. But soft! What light through yonder window breaks?",
      extractions: [
        {
          field: "character",
          extraction_text: "ROMEO",
          value: { name: "ROMEO" },
        },
      ],
    },
  ]);
});

test("document class drafts omit empty scenes from serialization", () => {
  const drafts = toDocumentClassDrafts([
    {
      id: "class-shakespeare",
      name: "Shakespeare",
      description: "",
      aliases: [],
      extraction_schema: {
        id: "schema-literature-fields",
        name: "literature_fields",
        description: "",
        fields: [
          {
            name: "character",
            dtype: "str",
            description: "Speaking character",
            required: false,
            fields: [],
            examples: [{ text: "ROMEO speaks.", value: "ROMEO", extraction_text: "ROMEO" }],
          },
        ],
      },
    },
  ]);

  const serialized = serializeDocumentClassDrafts(drafts) as Array<{
    extraction_schema: Record<string, unknown>;
  }>;
  assert.equal("scenes" in serialized[0].extraction_schema, false);
});

test("validateContentEnrichmentDrafts flags scene extractions referencing unknown fields", () => {
  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-shakespeare",
        name: "Shakespeare",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-literature-fields",
          name: "literature_fields",
          version: null,
          description: "",
          fields: [
            {
              name: "character",
              dtype: "object_list",
              description: "Speaking character",
              required: false,
              clustered_under_heading: true,
              fields: [
                { name: "name", dtype: "str", description: "Character name", required: true },
              ],
              examples: [
                {
                  text: "ROMEO speaks.",
                  value: "ROMEO",
                  extraction_text: "ROMEO",
                  child_values: { name: "ROMEO" },
                },
              ],
            },
          ],
          scenes: [
            {
              id: "scene-1",
              text: "ROMEO. But soft!",
              extractions: [
                {
                  id: "scene-ex-1",
                  field: "emotion",
                  extraction_text: "But soft!",
                  value: "wonder",
                  child_values: {},
                },
              ],
            },
          ],
        },
      },
    ]),
    "scene_extraction_field_unknown",
  );
});

test("validateContentEnrichmentDrafts rejects scene examples without values", () => {
  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-shakespeare",
        name: "Shakespeare",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-literature-fields",
          name: "literature_fields",
          version: null,
          description: "",
          fields: [
            {
              name: "character",
              dtype: "object_list",
              description: "Speaking character",
              required: false,
              clustered_under_heading: true,
              fields: [
                {
                  name: "name",
                  dtype: "str",
                  description: "Character name",
                  required: true,
                },
              ],
              examples: [],
            },
          ],
          scenes: [
            {
              id: "scene-1",
              text: "ROMEO. But soft!",
              extractions: [
                {
                  id: "scene-ex-1",
                  field: "character",
                  extraction_text: "ROMEO",
                  value: "",
                  child_values: {},
                },
              ],
            },
          ],
        },
      },
    ]),
    "field_example_required",
  );
});

test("validateContentEnrichmentDrafts allows extraction fields without examples", () => {
  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-permit",
        name: "Permit",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-permit-fields",
          name: "permit_fields",
          version: null,
          description: "",
          fields: [
            {
              name: "due_date",
              dtype: "date",
              description: "Global due date",
              required: true,
              clustered_under_heading: true,
              fields: [],
              examples: [],
            },
          ],
          scenes: [],
        },
      },
    ]),
    null,
  );
});

test("empty draft factories provide usable starter values", () => {
  const emptyClassDraft = createEmptyDocumentClassDraft();
  assert.equal(typeof emptyClassDraft.id, "string");
  assert.ok(emptyClassDraft.id.length > 0);
  assert.equal(emptyClassDraft.name, "");
  assert.equal(emptyClassDraft.version, null);
  assert.equal(emptyClassDraft.description, "");
  assert.equal(emptyClassDraft.aliases_text, "");
  assert.equal(emptyClassDraft.extraction_schema, null);

  assert.deepEqual(createEmptyExtractionFieldDraft(), {
    name: "",
    dtype: "str",
    description: "",
    required: false,
    clustered_under_heading: true,
    fields: [],
    examples: [],
  });

  const emptySchemaDraft = createEmptyExtractionSchemaDraft("Invoice");
  assert.equal(typeof emptySchemaDraft.id, "string");
  assert.ok(emptySchemaDraft.id.length > 0);
  assert.equal(emptySchemaDraft.name, "Invoice Fields");
  assert.equal(emptySchemaDraft.version, null);
  assert.equal(emptySchemaDraft.description, "");
  assert.deepEqual(emptySchemaDraft.fields, [
    {
      name: "",
      dtype: "str",
      description: "",
      required: false,
      clustered_under_heading: true,
      fields: [],
      examples: [],
    },
  ]);
});

test("content enrichment validation catches class, schema, and field problems", () => {
  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-invoice",
        name: "Invoice",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: null,
      },
      {
        id: "class-invoice-2",
        name: "invoice",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: null,
      },
    ]),
    "class_name_duplicate",
  );

  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-invoice",
        name: "Invoice",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-invoice-fields",
          name: "",
          version: null,
          description: "",
          fields: [],
          scenes: [],
        },
      },
    ]),
    "schema_name_required",
  );

  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-invoice",
        name: "Invoice",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-invoice-fields",
          name: "invoice_fields",
          version: null,
          description: "",
          fields: [
            {
              name: "invoice_number",
              dtype: "str",
              description: "",
              required: false,
              clustered_under_heading: true,
              fields: [],
              examples: [],
            },
          ],
          scenes: [],
        },
      },
    ]),
    "field_description_required",
  );

  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-permit",
        name: "Permit",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-permit-fields",
          name: "permit_fields",
          version: null,
          description: "",
          fields: [
            {
              name: "tasks",
              dtype: "object_list",
              description: "Tasks mentioned in the permit.",
              required: false,
              clustered_under_heading: true,
              fields: [
                {
                  name: "title",
                  dtype: "str",
                  description: "Task title",
                  required: true,
                },
              ],
              examples: [],
            },
          ],
          scenes: [],
        },
      },
    ]),
    null,
  );

  assert.equal(
    validateContentEnrichmentDrafts([
      {
        id: "class-permit",
        name: "Permit",
        version: null,
        description: "",
        aliases_text: "",
        extraction_schema: {
          id: "schema-permit-fields",
          name: "permit_fields",
          version: null,
          description: "",
          fields: [
            {
              name: "due_date",
              dtype: "date",
              description: "Global due date",
              required: false,
              clustered_under_heading: true,
              fields: [],
              examples: [],
            },
          ],
          scenes: [],
        },
      },
    ]),
    null,
  );
});

test("content enrichment queue summary normalizes stale counts", () => {
  assert.deepEqual(summarizeContentEnrichmentQueue(4), {
    staleCount: 4,
    hasStaleFiles: true,
  });

  assert.deepEqual(summarizeContentEnrichmentQueue(0), {
    staleCount: 0,
    hasStaleFiles: false,
  });

  assert.deepEqual(summarizeContentEnrichmentQueue(-3), {
    staleCount: 0,
    hasStaleFiles: false,
  });
});

test("content enrichment rerun summary normalizes queue results", () => {
  assert.deepEqual(summarizeContentEnrichmentRerun({ queued: 3, matched: 5, errors: 1 }), {
    queuedCount: 3,
    matchedCount: 5,
    errorCount: 1,
    hasQueuedFiles: true,
  });

  assert.deepEqual(
    summarizeContentEnrichmentRerun({ queued: -2, matched: Number.NaN, errors: -1 }),
    {
      queuedCount: 0,
      matchedCount: 0,
      errorCount: 0,
      hasQueuedFiles: false,
    },
  );
});
