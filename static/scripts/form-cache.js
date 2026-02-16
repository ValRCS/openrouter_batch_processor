(() => {
  const form = document.querySelector("form");
  if (!form) {
    return;
  }

  const scope =
    form.dataset.cacheScope ||
    (document.body && document.body.dataset.cacheScope) ||
    "default";
  const key = (suffix) => `${scope}_${suffix}`;

  const promptField = document.querySelector('textarea[name="system_prompt"]');
  const modelDropdown = document.querySelector('select[name="model_dropdown"]');
  const modelCustom = document.querySelector('input[name="model_custom"]');
  const apiKeyField = document.querySelector('input[name="api_key"]');
  const includeInputsField = document.querySelector('input[name="include_inputs"]');
  const includeMetadataField = document.querySelector('input[name="include_metadata"]');
  const separateOutputsField = document.querySelector('input[name="separate_outputs"]');
  const zipField = document.querySelector('input[name="zipfile"]');
  const existingZipField = document.querySelector('input[name="existing_zip"]');
  const existingZipButtons = Array.from(document.querySelectorAll("[data-existing-zip]"));
  const existingZipStatus = document.getElementById("existing-zip-status");

  let assigningExistingZip = false;

  const updateZipRequired = () => {
    if (!zipField) {
      return;
    }
    const hasUpload = zipField.files && zipField.files.length > 0;
    const hasExisting = existingZipField && existingZipField.value.trim() !== "";
    zipField.required = !(hasUpload || hasExisting);
  };

  const setExistingZipStatus = (message, isError = false) => {
    if (!existingZipStatus) {
      return;
    }
    existingZipStatus.textContent = message;
    existingZipStatus.classList.toggle("error", isError);
  };

  const setActiveExistingZip = (zipName) => {
    existingZipButtons.forEach((button) => {
      const isActive = zipName && button.dataset.existingZip === zipName;
      button.classList.toggle("active", Boolean(isActive));
    });
  };

  const storedPrompt = localStorage.getItem(key("system_prompt"));
  if (storedPrompt !== null && promptField) {
    promptField.value = storedPrompt;
  }

  const storedApiKey = localStorage.getItem(key("api_key"));
  if (storedApiKey !== null && apiKeyField) {
    apiKeyField.value = storedApiKey;
  }

  const storedModel = localStorage.getItem(key("model"));
  if (storedModel && (modelDropdown || modelCustom)) {
    let matchedDropdown = false;
    if (modelDropdown) {
      matchedDropdown = Array.from(modelDropdown.options).some(
        (option) => option.value === storedModel
      );
      if (matchedDropdown) {
        modelDropdown.value = storedModel;
        if (modelCustom) {
          modelCustom.value = "";
        }
      }
    }

    if (!matchedDropdown && modelCustom) {
      modelCustom.value = storedModel;
    }
  }

  const storedIncludeInputs = localStorage.getItem(key("include_inputs"));
  if (storedIncludeInputs !== null && includeInputsField) {
    includeInputsField.checked = storedIncludeInputs === "true";
  }

  const storedIncludeMetadata = localStorage.getItem(key("include_metadata"));
  if (storedIncludeMetadata !== null && includeMetadataField) {
    includeMetadataField.checked = storedIncludeMetadata === "true";
  }

  const storedSeparateOutputs = localStorage.getItem(key("separate_outputs"));
  if (storedSeparateOutputs !== null && separateOutputsField) {
    separateOutputsField.checked = storedSeparateOutputs === "true";
  }

  if (zipField && existingZipField) {
    updateZipRequired();

    zipField.addEventListener("change", () => {
      if (assigningExistingZip) {
        updateZipRequired();
        return;
      }

      const hasUpload = zipField.files && zipField.files.length > 0;
      if (hasUpload) {
        existingZipField.value = "";
        setActiveExistingZip("");
        setExistingZipStatus("");
      }
      updateZipRequired();
    });
  }

  if (existingZipButtons.length && zipField && existingZipField) {
    existingZipButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const zipName = button.dataset.existingZip || "";
        const zipUrl = button.dataset.zipUrl || "";
        if (!zipName || !zipUrl) {
          return;
        }

        existingZipField.value = zipName;
        setActiveExistingZip(zipName);
        setExistingZipStatus(`Selected existing ZIP: ${zipName}`);
        updateZipRequired();

        try {
          const response = await fetch(zipUrl, { cache: "no-store" });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const zipBlob = await response.blob();
          if (typeof DataTransfer === "undefined") {
            return;
          }

          assigningExistingZip = true;
          const file = new File([zipBlob], zipName, {
            type: "application/zip",
            lastModified: Date.now()
          });
          const dt = new DataTransfer();
          dt.items.add(file);
          zipField.files = dt.files;
          zipField.dispatchEvent(new Event("change", { bubbles: true }));
        } catch (error) {
          setExistingZipStatus(`Could not load ${zipName}.`, true);
        } finally {
          assigningExistingZip = false;
          updateZipRequired();
        }
      });
    });
  }

  form.addEventListener("submit", () => {
    if (apiKeyField) {
      localStorage.setItem(key("api_key"), apiKeyField.value);
    }

    if (promptField) {
      localStorage.setItem(key("system_prompt"), promptField.value);
    }

    const customValue = modelCustom ? modelCustom.value.trim() : "";
    const dropdownValue = modelDropdown ? modelDropdown.value : "";
    const chosenModel = customValue || dropdownValue;
    if (chosenModel) {
      localStorage.setItem(key("model"), chosenModel);
    }

    if (includeInputsField) {
      localStorage.setItem(key("include_inputs"), String(includeInputsField.checked));
    }

    if (includeMetadataField) {
      localStorage.setItem(key("include_metadata"), String(includeMetadataField.checked));
    }

    if (separateOutputsField) {
      localStorage.setItem(key("separate_outputs"), String(separateOutputsField.checked));
    }
  });
})();
