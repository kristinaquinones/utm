// Copyright (C) 2026 Kristina Quinones
// SPDX-License-Identifier: GPL-2.0-only

const STORAGE_KEYS = {
  dark: "utm_dark",
  view: "utm_view",
  mode: "utm_mode",
};

const MAX_BULK_LINKS = 50;

const STANDARD_UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
];

const customParamTemplate = () => {
  const row = document.createElement("div");
  row.className = "cp-row";
  row.innerHTML = `
    <input class="f-input" name="custom_key" type="text" placeholder="key">
    <input class="f-input" name="custom_value" type="text" placeholder="value">
    <button class="btn-icon" type="button" data-remove-param aria-label="Remove custom parameter">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
    </button>
  `;
  return row;
};

const getCsrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

const getJsonScript = (id) => {
  const element = document.getElementById(id);
  if (!element) {
    return [];
  }
  try {
    return JSON.parse(element.textContent || "[]");
  } catch {
    return [];
  }
};

const csvCell = (value) => {
  const text = String(value);
  if (/^[=+\-@\t\r\n]/.test(text)) {
    return `'${text}`;
  }
  return text;
};

const downloadCsv = (rows, filename) => {
  if (!rows.length) {
    return;
  }
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};

const syncTemplate = (template) => {
  if (!template) {
    return;
  }

  document.querySelectorAll("[data-param]").forEach((input) => {
    input.value = template.params[input.dataset.param] || "";
  });

  const customWrap = document.querySelector("[data-custom-params]");
  if (!customWrap) {
    return;
  }
  customWrap.innerHTML = "";

  const standardKeys = new Set(
    Array.from(document.querySelectorAll("[data-param]")).map((input) => input.dataset.param),
  );

  Object.entries(template.params)
    .filter(([key]) => !standardKeys.has(key))
    .forEach(([key, value]) => {
      const row = customParamTemplate();
      row.querySelector('input[name="custom_key"]').value = key;
      row.querySelector('input[name="custom_value"]').value = value;
      customWrap.append(row);
    });

  updateCustomParamsLabel();
  rebuildBulkParamOptions();
  highlightActiveTemplate(template.id);
};

const highlightActiveTemplate = (templateId) => {
  document.querySelectorAll(".tpl-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.templateId === templateId);
  });
};

const updateCustomParamsLabel = () => {
  const label = document.getElementById("custom-params-label");
  const count = document.querySelectorAll("[data-custom-params] .cp-row").length;
  if (label) {
    label.textContent = count > 0 ? `Custom parameters (${count})` : "Custom parameters";
  }
};

const rebuildBulkParamOptions = () => {
  const select = document.getElementById("f-bulk-param");
  if (!select) {
    return;
  }

  const current = select.value;
  const standardKeys = Array.from(document.querySelectorAll("[data-param]")).map(
    (input) => input.dataset.param,
  );
  const customKeys = Array.from(document.querySelectorAll('[name="custom_key"]'))
    .map((input) => input.value.trim())
    .filter(Boolean);

  select.innerHTML = "";
  [...standardKeys, ...customKeys].forEach((key) => {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = key;
    select.append(option);
  });

  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
};

const copyToClipboard = async (text, button) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }

  const announce = document.getElementById("copy-announce");
  if (announce) {
    announce.textContent = "Copied to clipboard";
  }

  if (!button) {
    return;
  }

  const defaultIcon = button.querySelector(".copy-icon-default");
  const doneIcon = button.querySelector(".copy-icon-done");
  if (defaultIcon && doneIcon) {
    defaultIcon.classList.add("hidden");
    doneIcon.classList.remove("hidden");
    window.setTimeout(() => {
      defaultIcon.classList.remove("hidden");
      doneIcon.classList.add("hidden");
    }, 2000);
  }
};

const showSaveSuccess = (message) => {
  const container = document.getElementById("save-success");
  const text = document.getElementById("save-success-text");
  if (!container || !text) {
    return;
  }
  text.textContent = `Saved "${message}"`;
  container.classList.add("visible");
  window.setTimeout(() => {
    container.classList.remove("visible");
  }, 3000);
};

const incrementLinksBadge = (count) => {
  const badge = document.getElementById("links-count-badge");
  if (!badge) {
    return;
  }
  badge.textContent = String(Number(badge.textContent || 0) + count);
  window.needsLinksRefresh = true;
};

const submitFormFetch = async (url, form) => {
  const formData = new FormData(form);
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "X-Requested-With": "fetch",
    },
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
};

const initTheme = () => {
  const toggle = document.getElementById("theme-toggle");
  const iconLight = document.getElementById("theme-icon-light");
  const iconDark = document.getElementById("theme-icon-dark");
  if (!toggle) {
    return;
  }

  const applyTheme = (dark) => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "");
    toggle.setAttribute("aria-pressed", String(dark));
    toggle.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    iconLight?.classList.toggle("hidden", dark);
    iconDark?.classList.toggle("hidden", !dark);
  };

  let dark = false;
  try {
    dark = localStorage.getItem(STORAGE_KEYS.dark) === "true";
  } catch {
    dark = false;
  }
  applyTheme(dark);

  toggle.addEventListener("click", () => {
    dark = !dark;
    try {
      localStorage.setItem(STORAGE_KEYS.dark, String(dark));
    } catch {
      /* ignore */
    }
    applyTheme(dark);
  });
};

const initTabs = () => {
  const builderTab = document.getElementById("nav-builder");
  const linksTab = document.getElementById("nav-links");
  const builderPanel = document.getElementById("view-builder");
  const linksPanel = document.getElementById("view-links");
  if (!builderTab || !linksTab || !builderPanel || !linksPanel) {
    return;
  }

  const setView = (view, { reloadLinks = false } = {}) => {
    if (view === "links" && reloadLinks && window.needsLinksRefresh) {
      try {
        localStorage.setItem(STORAGE_KEYS.view, "links");
      } catch {
        /* ignore */
      }
      window.location.reload();
      return;
    }

    builderTab.classList.toggle("active", view === "builder");
    linksTab.classList.toggle("active", view === "links");
    builderTab.setAttribute("aria-current", view === "builder" ? "page" : "false");
    linksTab.setAttribute("aria-current", view === "links" ? "page" : "false");
    builderPanel.classList.toggle("active", view === "builder");
    linksPanel.classList.toggle("active", view === "links");

    try {
      localStorage.setItem(STORAGE_KEYS.view, view);
    } catch {
      /* ignore */
    }
  };

  let initialView = "builder";
  try {
    initialView = localStorage.getItem(STORAGE_KEYS.view) || "builder";
  } catch {
    initialView = "builder";
  }
  setView(initialView === "links" ? "links" : "builder");

  builderTab.addEventListener("click", () => setView("builder"));
  linksTab.addEventListener("click", () => setView("links", { reloadLinks: true }));

  document.querySelectorAll("[data-go-builder]").forEach((button) => {
    button.addEventListener("click", () => setView("builder"));
  });

  document.getElementById("save-success-view-links")?.addEventListener("click", () => {
    setView("links", { reloadLinks: true });
  });

  window.setView = setView;
};

const countLines = (text) => text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).length;

const setFieldDisabled = (field, disabled) => {
  if (!field) {
    return;
  }
  field.disabled = disabled;
};

const prepareBulkFormData = (formData, mode) => {
  if (mode === "bulk") {
    formData.delete("base_url");
    const bulkBaseUrls = document.getElementById("f-bulk-base-urls");
    const bulkFallback = document.getElementById("bulk-fallback-url");
    if (bulkBaseUrls && !bulkBaseUrls.value.trim() && bulkFallback?.value.trim()) {
      formData.set("bulk_base_urls", bulkFallback.value.trim());
    }
    return formData;
  }
  formData.delete("bulk_key");
  formData.delete("bulk_values");
  formData.delete("bulk_base_urls");
  return formData;
};

const hasStandardUtm = () => {
  const hasBaseUtm = Array.from(document.querySelectorAll("[data-param]")).some(
    (input) => input.value.trim(),
  );
  if (hasBaseUtm) {
    return true;
  }

  const mode = window.getGenerationMode?.() || "single";
  if (mode !== "bulk") {
    return false;
  }

  const bulkKey = document.getElementById("f-bulk-param")?.value.trim() || "";
  const bulkValues = document.getElementById("f-bulk-values")?.value || "";
  return STANDARD_UTM_KEYS.includes(bulkKey) && countLines(bulkValues) > 0;
};

const updateFormValidity = () => {
  const validUtm = hasStandardUtm();
  const generateBtn = document.getElementById("generate-preview-btn");
  const saveSingle = document.getElementById("save-single");
  const saveBulk = document.getElementById("save-bulk");
  const hint = document.getElementById("utm-validity-hint");
  const urlField = document.getElementById("f-bulk-base-urls");
  const valuesField = document.getElementById("f-bulk-values");
  const urlCount = urlField ? countLines(urlField.value) : 0;
  const valuesCount = valuesField ? countLines(valuesField.value) : 0;
  const overLimit = urlCount > MAX_BULK_LINKS || valuesCount > MAX_BULK_LINKS;

  setFieldDisabled(generateBtn, !validUtm || overLimit);
  setFieldDisabled(saveSingle, !validUtm);
  setFieldDisabled(saveBulk, !validUtm || overLimit);

  if (hint) {
    hint.textContent = validUtm
      ? ""
      : "Add at least one standard UTM parameter (utm_source, utm_medium, utm_campaign, utm_term, or utm_content).";
    hint.classList.toggle("hidden", validUtm);
  }
};

const updateBulkLineCounts = () => {
  const urlField = document.getElementById("f-bulk-base-urls");
  const valuesField = document.getElementById("f-bulk-values");
  const urlCountEl = document.getElementById("bulk-url-line-count");
  const valuesCountEl = document.getElementById("bulk-values-line-count");

  const urlCount = urlField ? countLines(urlField.value) : 0;
  const valuesCount = valuesField ? countLines(valuesField.value) : 0;
  const overLimit = urlCount > MAX_BULK_LINKS || valuesCount > MAX_BULK_LINKS;

  if (urlCountEl) {
    if (urlCount > 0) {
      urlCountEl.textContent = `One link per line · ${urlCount} URL${urlCount === 1 ? "" : "s"}`;
    } else {
      urlCountEl.textContent = "One link per line. Leave empty when varying a parameter on one URL.";
    }
  }

  if (valuesCountEl) {
    if (valuesCount > 0) {
      valuesCountEl.textContent = `${valuesCount} value${valuesCount === 1 ? "" : "s"}`;
    } else {
      valuesCountEl.textContent = "";
    }
  }

  if (overLimit && urlCountEl) {
    urlCountEl.textContent = `Maximum ${MAX_BULK_LINKS} links allowed.`;
  }

  updateFormValidity();
};

const initModeToggle = () => {
  const singleBtn = document.getElementById("mode-single");
  const bulkBtn = document.getElementById("mode-bulk");
  const bulkSection = document.getElementById("bulk-section");
  const saveSingle = document.getElementById("save-single");
  const saveBulk = document.getElementById("save-bulk");
  const generationModeInput = document.getElementById("generation-mode");
  const singleFieldsRow = document.getElementById("single-fields-row");
  const bulkNameRow = document.getElementById("bulk-name-row");
  const singleUtmMount = document.getElementById("single-utm-mount");
  const bulkUtmMount = document.getElementById("bulk-utm-mount");
  const utmParams = document.getElementById("utm-params");
  const linkNameMount = document.getElementById("link-name-mount");
  const bulkNameMount = document.getElementById("bulk-name-mount");
  const linkNameLabel = document.getElementById("link-name-label");
  const linkNameInput = document.getElementById("link-name-input");
  const baseUrlInput = document.getElementById("utm-base-url");
  const bulkBaseUrls = document.getElementById("f-bulk-base-urls");
  const bulkKey = document.getElementById("f-bulk-param");
  const bulkValues = document.getElementById("f-bulk-values");

  if (!singleBtn || !bulkBtn || !bulkSection) {
    return;
  }

  const setMode = (mode) => {
    const isBulk = mode === "bulk";
    singleBtn.classList.toggle("active", !isBulk);
    bulkBtn.classList.toggle("active", isBulk);
    singleBtn.setAttribute("aria-pressed", String(!isBulk));
    bulkBtn.setAttribute("aria-pressed", String(isBulk));
    bulkSection.classList.toggle("visible", isBulk);
    saveSingle?.classList.toggle("hidden", isBulk);
    saveBulk?.classList.toggle("hidden", !isBulk);
    singleFieldsRow?.classList.toggle("hidden", isBulk);
    bulkNameRow?.classList.toggle("hidden", !isBulk);
    singleUtmMount?.classList.toggle("hidden", isBulk);

    if (generationModeInput) {
      generationModeInput.value = mode;
    }

    if (utmParams && singleUtmMount && bulkUtmMount) {
      if (isBulk) {
        bulkUtmMount.append(utmParams);
      } else {
        singleUtmMount.append(utmParams);
      }
    }

    if (linkNameInput && linkNameMount && bulkNameMount) {
      if (isBulk) {
        bulkNameMount.prepend(linkNameLabel);
        bulkNameMount.append(linkNameInput);
        linkNameLabel.textContent = "Name prefix";
        linkNameInput.placeholder = "Launch campaign";
      } else {
        linkNameMount.prepend(linkNameLabel);
        linkNameMount.append(linkNameInput);
        linkNameLabel.textContent = "Link name";
        linkNameInput.placeholder = "June newsletter";
      }
    }

    setFieldDisabled(baseUrlInput, isBulk);
    setFieldDisabled(bulkBaseUrls, !isBulk);
    setFieldDisabled(bulkKey, !isBulk);
    setFieldDisabled(bulkValues, !isBulk);

    if (isBulk && bulkBaseUrls && !bulkBaseUrls.value.trim() && baseUrlInput?.value.trim()) {
      bulkBaseUrls.value = baseUrlInput.value.trim();
    }

    updateBulkLineCounts();

    try {
      localStorage.setItem(STORAGE_KEYS.mode, mode);
    } catch {
      /* ignore */
    }

    updateFormValidity();
  };

  let initialMode = "single";
  if (generationModeInput?.value === "bulk") {
    initialMode = "bulk";
  } else {
    try {
      initialMode = localStorage.getItem(STORAGE_KEYS.mode) || "single";
    } catch {
      initialMode = "single";
    }
  }
  setMode(initialMode === "bulk" ? "bulk" : "single");

  singleBtn.addEventListener("click", () => setMode("single"));
  bulkBtn.addEventListener("click", () => setMode("bulk"));

  bulkBaseUrls?.addEventListener("input", updateBulkLineCounts);
  bulkValues?.addEventListener("input", updateBulkLineCounts);
  bulkKey?.addEventListener("change", updateFormValidity);

  document.querySelectorAll("[data-param]").forEach((input) => {
    input.addEventListener("input", updateFormValidity);
  });

  window.getGenerationMode = () => generationModeInput?.value || "single";
};

const initCollapsibles = () => {
  const toggles = [
    {
      button: document.getElementById("toggle-custom-params"),
      panel: document.getElementById("panel-custom-params"),
      chevron: document.getElementById("custom-params-chevron"),
    },
    {
      button: document.getElementById("toggle-save-template"),
      panel: document.getElementById("panel-save-template"),
      chevron: document.getElementById("save-template-chevron"),
    },
  ];

  toggles.forEach(({ button, panel, chevron }) => {
    if (!button || !panel) {
      return;
    }

    button.addEventListener("click", () => {
      const open = panel.classList.toggle("open");
      button.setAttribute("aria-expanded", String(open));
      chevron?.classList.toggle("open", open);
    });
  });
};

const initGeneratorForm = () => {
  const form = document.getElementById("generator-form");
  if (!form) {
    return;
  }

  form.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-param]");
    if (addButton) {
      const wrap = form.querySelector("[data-custom-params]");
      wrap?.append(customParamTemplate());
      updateCustomParamsLabel();
      rebuildBulkParamOptions();
      return;
    }

    const removeButton = event.target.closest("[data-remove-param]");
    if (removeButton) {
      removeButton.closest(".cp-row")?.remove();
      updateCustomParamsLabel();
      rebuildBulkParamOptions();
      return;
    }

    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      copyToClipboard(copyButton.dataset.copy || "", copyButton);
    }
  });

  form.addEventListener("input", (event) => {
    if (event.target.matches('[name="custom_key"]')) {
      rebuildBulkParamOptions();
      updateCustomParamsLabel();
    }
    if (event.target.matches("[data-param]")) {
      updateFormValidity();
    }
  });

  form.addEventListener("change", (event) => {
    if (event.target.matches("[data-param]")) {
      updateFormValidity();
    }
  });

  form.addEventListener("submit", () => {
    const mode = window.getGenerationMode?.() || "single";
    const generationModeInput = document.getElementById("generation-mode");
    if (generationModeInput) {
      generationModeInput.value = mode;
    }
    if (mode === "bulk") {
      const bulkBaseUrls = document.getElementById("f-bulk-base-urls");
      const bulkFallback = document.getElementById("bulk-fallback-url");
      if (bulkBaseUrls && !bulkBaseUrls.value.trim() && bulkFallback?.value.trim()) {
        bulkBaseUrls.value = bulkFallback.value.trim();
      }
    }
  });

  document.getElementById("save-single")?.addEventListener("click", async () => {
    const formData = new FormData(form);
    const mode = window.getGenerationMode?.() || "single";
    formData.set("generation_mode", mode);
    formData.set("save_mode", "single");
    prepareBulkFormData(formData, mode);
    try {
      const result = await fetch("/links", {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: formData,
      }).then((response) => response.json());
      if (!result.ok) {
        return;
      }
      showSaveSuccess(result.names?.[0] || "link");
      incrementLinksBadge(result.count || 1);
    } catch {
      /* ignore */
    }
  });

  document.getElementById("save-bulk")?.addEventListener("click", async () => {
    const formData = new FormData(form);
    const mode = window.getGenerationMode?.() || "bulk";
    formData.set("generation_mode", mode);
    formData.set("save_mode", "bulk");
    prepareBulkFormData(formData, mode);
    try {
      const response = await fetch("/links", {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: formData,
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        return;
      }
      const label = `${result.count || 0} link${result.count === 1 ? "" : "s"}`;
      showSaveSuccess(label);
      incrementLinksBadge(result.count || 0);
    } catch {
      /* ignore */
    }
  });

  document.getElementById("save-template-btn")?.addEventListener("click", async () => {
    const formData = new FormData(form);
    try {
      await fetch("/templates", {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: formData,
      });
      window.location.reload();
    } catch {
      /* ignore */
    }
  });
};

const initTemplates = () => {
  const select = document.getElementById("template-select");
  const templates = getJsonScript("templates-data");

  select?.addEventListener("change", (event) => {
    const template = templates.find((item) => item.id === event.target.value);
    syncTemplate(template);
  });

  document.querySelectorAll("[data-apply-template]").forEach((button) => {
    button.addEventListener("click", () => {
      const template = templates.find((item) => item.id === button.dataset.applyTemplate);
      if (!select || !template) {
        return;
      }
      select.value = template.id;
      syncTemplate(template);
    });
  });
};

const initSavedLinks = () => {
  const filterInput = document.getElementById("f-links-filter");
  const selectAll = document.getElementById("cb-select-all");
  const selectAllLabel = document.getElementById("select-all-label");
  const clearBtn = document.getElementById("clear-selection-btn");
  const deleteBtn = document.getElementById("delete-selected-btn");
  const exportSelectedBtn = document.getElementById("export-selected-btn");
  const exportAllBtn = document.getElementById("export-all-btn");
  const linksList = document.getElementById("links-list");
  const emptyAll = document.getElementById("links-empty-all");
  const emptyFilter = document.getElementById("links-empty-filter");
  const filterQueryDisplay = document.getElementById("filter-query-display");

  if (!linksList) {
    return;
  }

  let linksData = getJsonScript("links-data");
  const selectedLinks = new Set();

  const getRows = () => Array.from(linksList.querySelectorAll(".links-row"));

  const matchesFilter = (row, query) => {
    if (!query) {
      return true;
    }
    const lower = query.toLowerCase();
    return (
      (row.dataset.linkName || "").includes(lower) ||
      (row.dataset.linkUrl || "").includes(lower)
    );
  };

  const visibleRows = () => getRows().filter((row) => !row.classList.contains("hidden"));

  const updateSelectionUi = () => {
    const visible = visibleRows();
    const visibleSelected = visible.filter((row) => selectedLinks.has(row.dataset.linkId));
    const count = visibleSelected.length;

    selectAllLabel.textContent =
      count === 0
        ? `${visible.length} link${visible.length === 1 ? "" : "s"}`
        : `${count} of ${visible.length} selected`;

    if (selectAll) {
      selectAll.checked = visible.length > 0 && count === visible.length;
      selectAll.indeterminate = count > 0 && count < visible.length;
    }

    deleteBtn?.classList.toggle("hidden", count === 0);
    exportSelectedBtn?.classList.toggle("hidden", count === 0);
    clearBtn?.classList.toggle("hidden", count === 0);

    const deleteCount = document.getElementById("delete-selected-count");
    const exportCount = document.getElementById("export-selected-count");
    if (deleteCount) {
      deleteCount.textContent = String(count);
    }
    if (exportCount) {
      exportCount.textContent = String(count);
    }

    getRows().forEach((row) => {
      row.classList.toggle("selected", selectedLinks.has(row.dataset.linkId));
      const checkbox = row.querySelector(".link-cb");
      if (checkbox) {
        checkbox.checked = selectedLinks.has(row.dataset.linkId);
      }
    });
  };

  const applyFilter = () => {
    const query = filterInput?.value.trim() || "";
    let visibleCount = 0;

    getRows().forEach((row) => {
      const visible = matchesFilter(row, query);
      row.classList.toggle("hidden", !visible);
      if (visible) {
        visibleCount += 1;
      }
    });

    const total = getRows().length;
    emptyAll?.classList.toggle("hidden", total > 0);
    emptyFilter?.classList.toggle("hidden", total === 0 || visibleCount > 0 || !query);
    linksList.classList.toggle("hidden", total > 0 && visibleCount === 0 && !!query);

    if (filterQueryDisplay && query) {
      filterQueryDisplay.textContent = `"${query}"`;
    }

    updateSelectionUi();
  };

  filterInput?.addEventListener("input", applyFilter);

  selectAll?.addEventListener("change", () => {
    const visible = visibleRows();
    const allSelected = visible.every((row) => selectedLinks.has(row.dataset.linkId));
    if (allSelected) {
      visible.forEach((row) => selectedLinks.delete(row.dataset.linkId));
    } else {
      visible.forEach((row) => selectedLinks.add(row.dataset.linkId));
    }
    updateSelectionUi();
  });

  clearBtn?.addEventListener("click", () => {
    selectedLinks.clear();
    updateSelectionUi();
  });

  linksList.addEventListener("change", (event) => {
    const checkbox = event.target.closest(".link-cb");
    if (!checkbox) {
      return;
    }
    const row = checkbox.closest(".links-row");
    if (!row) {
      return;
    }
    if (checkbox.checked) {
      selectedLinks.add(row.dataset.linkId);
    } else {
      selectedLinks.delete(row.dataset.linkId);
    }
    updateSelectionUi();
  });

  linksList.addEventListener("click", (event) => {
    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      copyToClipboard(copyButton.dataset.copy || "", copyButton);
    }
  });

  deleteBtn?.addEventListener("click", async () => {
    if (selectedLinks.size === 0) {
      return;
    }
    const formData = new FormData();
    formData.set("csrf_token", getCsrfToken());
    selectedLinks.forEach((id) => formData.append("link_ids", id));

    try {
      await fetch("/links/bulk-delete", {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: formData,
      });
      window.location.reload();
    } catch {
      /* ignore */
    }
  });

  exportSelectedBtn?.addEventListener("click", () => {
    const rows = linksData.filter((link) => selectedLinks.has(link.id));
    downloadCsv(
      [["Name", "URL", "Created"], ...rows.map((link) => [csvCell(link.name), csvCell(link.url), csvCell(link.created)])],
      `utm-links-${new Date().toISOString().slice(0, 10)}.csv`,
    );
  });

  exportAllBtn?.addEventListener("click", () => {
    downloadCsv(
      [["Name", "URL", "Created"], ...linksData.map((link) => [csvCell(link.name), csvCell(link.url), csvCell(link.created)])],
      `utm-links-${new Date().toISOString().slice(0, 10)}.csv`,
    );
  });

  applyFilter();
  updateSelectionUi();
};

document.addEventListener("DOMContentLoaded", () => {
  window.needsLinksRefresh = false;
  initTheme();
  initTabs();
  initModeToggle();
  initCollapsibles();
  initGeneratorForm();
  initTemplates();
  initSavedLinks();
  updateCustomParamsLabel();
  updateFormValidity();
});
