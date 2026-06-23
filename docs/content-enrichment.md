# Content Enrichment

Content enrichment adds document classification and structured extraction on top
of parsed content. It is configured through the admin settings UI and executed
by workers during processing.

## Catalog

The content enrichment catalog contains document classes. Each class can have
one extraction schema.

Document class fields:

- `id`
- `name`
- `description`
- `aliases`
- `version`
- optional `extraction_schema`

Extraction schema fields:

- `id`
- `name`
- `description`
- `version`
- `fields`
- `scenes`

Class and schema versions are separate. Class metadata changes increment the
class version. Schema content changes increment the schema version. Schema
versioning includes fields and shared scenes.

## Classification

Classification assigns a configured content class to a content item. The runtime
labels come from the catalog and are exposed to workers through backend runtime
config.

Classification is GLiNER2-backed. It is useful for:

- Routing content to class-specific extraction schemas.
- Filtering/reviewing content by class.
- Triggering stale enrichment when class definitions change.

## Extraction

Structured extraction uses the chat extraction provider (`langgraph_extract`).
The worker builds a schema-specific JSON prompt, calls the backend LLM proxy, and
normalizes the answer into field results with source evidence.

This is now the only supported extraction path. The older GLiNER2 and
LangExtract extraction providers were removed to keep schema behavior and
maintenance focused on one path.

Chat extraction supports:

- Scalar fields such as strings, dates, numbers, currencies, and booleans.
- Plain `list` fields.
- `object_list` fields with scalar/list child fields.
- Per-field examples and shared multi-field scenes.
- Evidence anchors that are grounded back to stored chunks when possible.

## Schema Design

Prefer flat repeated records over deeply nested objects. The current schema
supports an `object_list` with scalar/list child fields, but not nested
`object_list` inside another `object_list`.

Example for German cadastral references:

```json
{
  "name": "land_parcels",
  "dtype": "object_list",
  "fields": [
    { "name": "gemarkung", "dtype": "str" },
    { "name": "flur", "dtype": "str" },
    { "name": "flurstueck", "dtype": "str" }
  ]
}
```

Even though the real-world relationship is hierarchical, a flat row is better
for extraction, review, evidence, and deduplication:

```json
[
  {
    "gemarkung": "Musterstadt",
    "flur": "12",
    "flurstueck": "34/5"
  },
  {
    "gemarkung": "Musterstadt",
    "flur": "12",
    "flurstueck": "34/6"
  }
]
```

For heterogeneous lists such as `Nebenbestimmungen`, use a plain `list` field
when each item can remain a verbatim obligation. Use `object_list` only when you
need stable subfields per item.

## Examples And Scenes

Per-field examples are useful when one field needs standalone examples. They use:

- `text`: the source passage.
- `extraction_text`: the exact anchor phrase inside `text`.
- `value`: the expected extracted value.

Shared scenes are better when one source passage grounds multiple fields or
records. A scene contains:

- `text`: the source passage.
- `extractions`: field name, exact anchor text, and expected value.

For boundary-sensitive lists, include the first following non-target section in
the example text but exclude it from the expected value. This teaches the model
where to stop.

## Chunk Strategy

`document_extraction_chunk_strategy` controls chat extraction context selection:

- `full`: send all normalized text while it stays under the configured full-text
  threshold. This favors recall for demos and smaller documents.
- `selected`: use semantic/lexical chunk selection for larger workloads.

## Model Output Diagnostics

If the extraction LLM returns an empty assistant message or truncates JSON, the
worker raises/logs diagnostics that include finish reason, model, and max token
budget. Common causes are:

- Output token budget too low.
- Reasoning disabled for a model that needs it to understand section boundaries.
- Prompt/context too broad, causing over-extraction.
- Model/backend does not handle JSON response mode well.

Start by enabling extraction thinking for reasoning models and checking whether
the schema examples teach the correct boundaries. Then adjust
`document_extraction_llm_max_output_tokens`, chunk strategy, or model choice.
