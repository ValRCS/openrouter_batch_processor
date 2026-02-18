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
  const existingFolderField = document.querySelector('input[name="existing_folder"]');
  const existingFolderButtons = Array.from(document.querySelectorAll("[data-existing-folder]"));
  const existingFolderStatus = document.getElementById("existing-folder-status");

  const updateZipRequired = () => {
    if (!zipField) {
      return;
    }
    const hasUpload = zipField.files && zipField.files.length > 0;
    const hasExisting = existingZipField && existingZipField.value.trim() !== "";
    const hasFolder = existingFolderField && existingFolderField.value.trim() !== "";
    zipField.required = !(hasUpload || hasExisting || hasFolder);
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

  const setExistingFolderStatus = (message, isError = false) => {
    if (!existingFolderStatus) {
      return;
    }
    existingFolderStatus.textContent = message;
    existingFolderStatus.classList.toggle("error", isError);
  };

  const setActiveExistingFolder = (folderName) => {
    existingFolderButtons.forEach((button) => {
      const isActive = folderName && button.dataset.existingFolder === folderName;
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

  if (zipField) {
    updateZipRequired();

    zipField.addEventListener("change", () => {
      const hasUpload = zipField.files && zipField.files.length > 0;
      if (hasUpload) {
        if (existingZipField) {
          existingZipField.value = "";
        }
        setActiveExistingZip("");
        setExistingZipStatus("");
        if (existingFolderField) {
          existingFolderField.value = "";
        }
        setActiveExistingFolder("");
        setExistingFolderStatus("");
      }
      updateZipRequired();
    });
  }

  if (existingZipButtons.length && zipField && existingZipField) {
    existingZipButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const zipName = button.dataset.existingZip || "";
        if (!zipName) {
          return;
        }

        zipField.value = "";
        existingZipField.value = zipName;
        setActiveExistingZip(zipName);
        setExistingZipStatus(`Selected existing ZIP: ${zipName}`);
        if (existingFolderField) {
          existingFolderField.value = "";
        }
        setActiveExistingFolder("");
        setExistingFolderStatus("");
        updateZipRequired();
      });
    });
  }

  if (existingFolderButtons.length && zipField && existingFolderField) {
    existingFolderButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const folderName = button.dataset.existingFolder || "";
        if (!folderName) {
          return;
        }

        zipField.value = "";
        existingFolderField.value = folderName;
        setActiveExistingFolder(folderName);
        setExistingFolderStatus(`Selected folder: ${folderName}/`);
        if (existingZipField) {
          existingZipField.value = "";
        }
        setActiveExistingZip("");
        setExistingZipStatus("");
        updateZipRequired();
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
