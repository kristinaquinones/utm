const customParamTemplate = () => {
  const row = document.createElement("div");
  row.className = "param-row";
  row.innerHTML = `
    <input name="custom_key" placeholder="key">
    <input name="custom_value" placeholder="value">
    <button class="icon-button" type="button" data-remove-param aria-label="Remove custom parameter">x</button>
  `;
  return row;
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
};

document.addEventListener("click", async (event) => {
  const addButton = event.target.closest("[data-add-param]");
  if (addButton) {
    const wrap = addButton.closest("form").querySelector("[data-custom-params]");
    wrap.append(customParamTemplate());
    return;
  }

  const removeButton = event.target.closest("[data-remove-param]");
  if (removeButton) {
    removeButton.closest(".param-row").remove();
    return;
  }

  const copyButton = event.target.closest("[data-copy]");
  if (copyButton) {
    await navigator.clipboard.writeText(copyButton.dataset.copy);
    const original = copyButton.textContent;
    copyButton.textContent = "Copied";
    window.setTimeout(() => {
      copyButton.textContent = original;
    }, 1200);
  }
});

document.addEventListener("change", (event) => {
  if (event.target.id !== "template-select") {
    return;
  }

  const dataEl = document.getElementById("templates-data");
  if (!dataEl) {
    return;
  }

  const templates = JSON.parse(dataEl.textContent || "[]");
  syncTemplate(templates.find((template) => template.id === event.target.value));
});
