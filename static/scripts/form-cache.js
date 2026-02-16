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
