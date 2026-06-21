import assert from "node:assert/strict";
import test from "node:test";

import { contentApi } from "../api/content.ts";

test("content API builds extracted-data CSV URLs from active filters", () => {
  const url = contentApi.getExtractedDataCsvUrl({
    name: "invoice-[0-9]+",
    name_regex: true,
    search_path: true,
    document_class: "Invoice",
    extraction_schema: "invoice_fields",
    extraction_field: "invoice_number",
    field_filters: '[{"field":"invoice_number","op":"contains","value":"RE-1","dtype":"str"}]',
    review_status: "corrected",
    needs_review: true,
    stale_enrichment: true,
  });

  assert.equal(
    url,
    "/api/content/extracted-data.csv?name=invoice-%5B0-9%5D%2B&name_regex=true&search_path=true&document_class=Invoice&extraction_schema=invoice_fields&extraction_field=invoice_number&field_filters=%5B%7B%22field%22%3A%22invoice_number%22%2C%22op%22%3A%22contains%22%2C%22value%22%3A%22RE-1%22%2C%22dtype%22%3A%22str%22%7D%5D&review_status=corrected&needs_review=true&stale_enrichment=true",
  );
});
