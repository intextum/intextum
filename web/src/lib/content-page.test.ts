import assert from "node:assert/strict";
import test from "node:test";

import {
  applyContentPageReviewStatusFilterChange,
  applyContentPageViewModeChange,
  buildContentPageAllFilesViewProps,
  buildContentPageContentRenderModel,
  buildContentPageDialogModel,
  buildContentPageHeaderActions,
  buildContentPageHeaderBreadcrumbItems,
  buildContentPageContentState,
  buildContentPageHeaderState,
  readContentPageUrlState,
  type BuildContentPageAllFilesViewPropsOptions,
} from "./content-page.ts";

function createAllFilesViewPropsOptions(
  overrides: Partial<BuildContentPageAllFilesViewPropsOptions> = {},
): BuildContentPageAllFilesViewPropsOptions {
  return {
    viewMode: "all",
    currentPath: "",
    allFilesDocumentClassFilter: "",
    allFilesExtractionSchemaFilter: "",
    allFilesExtractionFieldFilter: "",
    allFilesFieldFilters: "",
    allFilesStaleOnly: false,
    allFilesStatusFilter: "",
    allFilesReviewStatusFilter: "",
    allFilesSearchMode: "exact",
    allFilesInitialQuery: "",
    refreshKey: 0,
    onNavigate: () => undefined,
    onImmutableChange: () => undefined,
    onFileClick: () => undefined,
    onProcess: async () => true,
    onSearchModeChange: () => undefined,
    onDocumentClassFilterChange: () => undefined,
    onExtractionSchemaFilterChange: () => undefined,
    onExtractionFieldFilterChange: () => undefined,
    onFieldFiltersChange: () => undefined,
    onStaleOnlyChange: () => undefined,
    onStatusFilterChange: () => undefined,
    onReviewStatusFilterChange: () => undefined,
    onProcessSelected: async () => undefined,
    ...overrides,
  };
}

test("readContentPageUrlState reads the review status filter from the url", () => {
  const state = readContentPageUrlState(
    new URLSearchParams("review_status=unreviewed&path=inbox/permits"),
  );

  assert.equal(state.allFilesReviewStatusFilter, "unreviewed");
  assert.deepEqual(state.pathParts, ["inbox", "permits"]);
  assert.deepEqual(state.breadcrumbPaths, ["inbox", "inbox/permits"]);
});

test("applyContentPageViewModeChange sets the view and clears file selection", () => {
  const params = new URLSearchParams("path=inbox&file=inbox/doc.pdf");

  applyContentPageViewModeChange(params, "all");

  assert.equal(params.get("view"), "all");
  assert.equal(params.get("file"), null);
});

test("applyContentPageReviewStatusFilterChange sets and clears the review status param", () => {
  const params = new URLSearchParams();
  applyContentPageReviewStatusFilterChange(params, "accepted");
  assert.equal(params.get("review_status"), "accepted");

  applyContentPageReviewStatusFilterChange(params, "");
  assert.equal(params.get("review_status"), null);
});

test("buildContentPageHeaderState always shows a single content header with shared breadcrumbs", () => {
  const browseState = buildContentPageHeaderState({
    currentPath: "inbox/contracts",
    isImmutable: false,
  });

  assert.deepEqual(browseState, {
    showViewTabs: false,
    showTitle: true,
    showBrowseBreadcrumbs: true,
    showBrowseActions: true,
  });

  const readonlyRootState = buildContentPageHeaderState({
    currentPath: "",
    isImmutable: true,
  });

  assert.deepEqual(readonlyRootState, {
    showViewTabs: false,
    showTitle: true,
    showBrowseBreadcrumbs: true,
    showBrowseActions: false,
  });
});

test("buildContentPageHeaderState keeps the single-shell title outside browse-focused links too", () => {
  const state = buildContentPageHeaderState({
    currentPath: "inbox/contracts",
    isImmutable: false,
  });

  assert.deepEqual(state, {
    showViewTabs: false,
    showTitle: true,
    showBrowseBreadcrumbs: true,
    showBrowseActions: true,
  });
});

test("buildContentPageHeaderBreadcrumbItems exposes root and nested crumbs for the unified page", () => {
  const nestedItems = buildContentPageHeaderBreadcrumbItems({
    pathParts: ["inbox", "contracts"],
    breadcrumbPaths: ["inbox", "inbox/contracts"],
  });

  assert.deepEqual(nestedItems, [
    {
      key: "root",
      label: "custom.root",
      path: "",
      isCurrent: false,
      isRoot: true,
    },
    {
      key: "inbox",
      label: "inbox",
      path: "inbox",
      isCurrent: false,
      isRoot: false,
    },
    {
      key: "inbox/contracts",
      label: "contracts",
      path: "inbox/contracts",
      isCurrent: true,
      isRoot: false,
    },
  ]);

  const rootOnlyItems = buildContentPageHeaderBreadcrumbItems({
    pathParts: [],
    breadcrumbPaths: [],
  });
  assert.deepEqual(rootOnlyItems, [
    {
      key: "root",
      label: "custom.root",
      path: "",
      isCurrent: true,
      isRoot: true,
    },
  ]);

  assert.deepEqual(
    buildContentPageHeaderBreadcrumbItems({
      pathParts: ["inbox"],
      breadcrumbPaths: ["inbox"],
    }),
    [
      {
        key: "root",
        label: "custom.root",
        path: "",
        isCurrent: false,
        isRoot: true,
      },
      {
        key: "inbox",
        label: "inbox",
        path: "inbox",
        isCurrent: true,
        isRoot: false,
      },
    ],
  );
});

test("buildContentPageHeaderBreadcrumbItems collapses long content paths", () => {
  assert.deepEqual(
    buildContentPageHeaderBreadcrumbItems({
      pathParts: ["root-folder", "2026", "clients", "permits", "signed"],
      breadcrumbPaths: [
        "root-folder",
        "root-folder/2026",
        "root-folder/2026/clients",
        "root-folder/2026/clients/permits",
        "root-folder/2026/clients/permits/signed",
      ],
    }),
    [
      {
        key: "root",
        label: "custom.root",
        path: "",
        isCurrent: false,
        isRoot: true,
      },
      {
        key: "ellipsis",
        label: "...",
        path: "",
        isCurrent: false,
        isRoot: false,
        isEllipsis: true,
      },
      {
        key: "root-folder/2026/clients",
        label: "clients",
        path: "root-folder/2026/clients",
        isCurrent: false,
        isRoot: false,
      },
      {
        key: "root-folder/2026/clients/permits",
        label: "permits",
        path: "root-folder/2026/clients/permits",
        isCurrent: false,
        isRoot: false,
      },
      {
        key: "root-folder/2026/clients/permits/signed",
        label: "signed",
        path: "root-folder/2026/clients/permits/signed",
        isCurrent: true,
        isRoot: false,
      },
    ],
  );
});

test("buildContentPageHeaderActions keep refresh always visible and gate path-scoped actions", () => {
  assert.deepEqual(
    buildContentPageHeaderActions({
      currentPath: "inbox/contracts",
      isImmutable: false,
    }),
    ["upload", "mkdir", "refresh"],
  );

  assert.deepEqual(
    buildContentPageHeaderActions({
      currentPath: "",
      isImmutable: false,
    }),
    ["refresh"],
  );

  assert.deepEqual(
    buildContentPageHeaderActions({
      currentPath: "inbox/contracts",
      isImmutable: false,
    }),
    ["upload", "mkdir", "refresh"],
  );
});

test("buildContentPageContentState keeps one unified workspace with folder browsing enabled", () => {
  const reviewState = buildContentPageContentState({
    isImmutable: false,
    hasDeleteHandler: true,
  });

  assert.deepEqual(reviewState, {
    showReviewWorkspace: false,
    showBrowseExplorer: true,
    showAllFilesView: true,
    canDeleteFromBrowse: true,
    canDeleteFromReview: false,
  });

  const readonlyReviewState = buildContentPageContentState({
    isImmutable: false,
    hasDeleteHandler: true,
  });
  assert.equal(readonlyReviewState.canDeleteFromReview, false);

  const browseState = buildContentPageContentState({
    isImmutable: false,
    hasDeleteHandler: true,
  });
  assert.equal(browseState.showBrowseExplorer, true);
  assert.equal(browseState.canDeleteFromBrowse, true);

  const allState = buildContentPageContentState({
    isImmutable: false,
    hasDeleteHandler: true,
  });
  assert.deepEqual(allState, {
    showReviewWorkspace: false,
    showBrowseExplorer: true,
    showAllFilesView: true,
    canDeleteFromBrowse: true,
    canDeleteFromReview: false,
  });
});

test("buildContentPageContentRenderModel always returns the unified content workspace shell", () => {
  const reviewModel = buildContentPageContentRenderModel({
    currentPath: "inbox/contracts",
    refreshKey: 4,
    isImmutable: false,
    hasDeleteHandler: true,
  });

  assert.deepEqual(reviewModel, {
    surface: "all",
    explorerKey: "inbox/contracts-4",
    canDeleteFromBrowse: true,
    canDeleteFromReview: false,
  });

  const browseModel = buildContentPageContentRenderModel({
    currentPath: "inbox/contracts",
    refreshKey: 4,
    isImmutable: false,
    hasDeleteHandler: true,
  });

  assert.deepEqual(browseModel, {
    surface: "all",
    explorerKey: "inbox/contracts-4",
    canDeleteFromBrowse: true,
    canDeleteFromReview: false,
  });

  const readonlyBrowseModel = buildContentPageContentRenderModel({
    currentPath: "inbox/contracts",
    refreshKey: 9,
    isImmutable: true,
    hasDeleteHandler: true,
  });
  assert.equal(readonlyBrowseModel.canDeleteFromBrowse, false);
  assert.equal(readonlyBrowseModel.explorerKey, "inbox/contracts-9");

  const allModel = buildContentPageContentRenderModel({
    currentPath: "inbox/contracts",
    refreshKey: 4,
    isImmutable: false,
    hasDeleteHandler: true,
  });

  assert.deepEqual(allModel, {
    surface: "all",
    explorerKey: "inbox/contracts-4",
    canDeleteFromBrowse: true,
    canDeleteFromReview: false,
  });
});

test("buildContentPageDialogModel keeps the content details dialog available across the unified page", () => {
  const reviewModel = buildContentPageDialogModel({
    selectedFilePath: "inbox/contracts/doc.pdf",
    selectedFileImmutable: false,
  });

  assert.deepEqual(reviewModel, {
    showFileDetailsDialog: true,
    fileDetailsOpen: true,
    canDeleteFromFileDetails: true,
  });

  const browseModel = buildContentPageDialogModel({
    selectedFilePath: "inbox/contracts/doc.pdf",
    selectedFileImmutable: false,
  });

  assert.deepEqual(browseModel, {
    showFileDetailsDialog: true,
    fileDetailsOpen: true,
    canDeleteFromFileDetails: true,
  });

  const readonlyAllModel = buildContentPageDialogModel({
    selectedFilePath: "inbox/contracts/doc.pdf",
    selectedFileImmutable: true,
  });

  assert.deepEqual(readonlyAllModel, {
    showFileDetailsDialog: true,
    fileDetailsOpen: true,
    canDeleteFromFileDetails: false,
  });

  const noSelectionModel = buildContentPageDialogModel({
    selectedFilePath: null,
    selectedFileImmutable: false,
  });
  assert.equal(noSelectionModel.fileDetailsOpen, false);
});

test("buildContentPageAllFilesViewProps preserves filters and handlers", () => {
  const options = createAllFilesViewPropsOptions({
    allFilesDocumentClassFilter: "Invoice",
    allFilesExtractionSchemaFilter: "invoice_fields",
    allFilesExtractionFieldFilter: "invoice_number",
    allFilesFieldFilters:
      '[{"field":"invoice_number","op":"contains","value":"INV-42","dtype":"str"}]',
    allFilesStaleOnly: true,
    allFilesStatusFilter: "COMPLETED",
    allFilesReviewStatusFilter: "unreviewed",
    refreshKey: 7,
  });

  const props = buildContentPageAllFilesViewProps(options);

  assert.equal(props.initialSortBy, "name");
  assert.equal(props.initialDocumentClassFilter, "Invoice");
  assert.equal(
    props.initialFieldFilters,
    '[{"field":"invoice_number","op":"contains","value":"INV-42","dtype":"str"}]',
  );
  assert.equal(props.initialReviewStatusFilter, "unreviewed");
  assert.equal(props.refreshKey, 7);
  assert.equal(props.onFileClick, options.onFileClick);
  assert.equal(props.onProcessSelected, options.onProcessSelected);
});
