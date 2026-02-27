(() => {
  const STORAGE_KEY = "marc_ui_language";
  const SUPPORTED = ["en", "lv"];
  const DEFAULT_LANGUAGE = "en";

  const translations = {
    en: {
      "language.label": "Language:",
      "language.english": "English",
      "language.latvian": "Latvie\u0161u",
      "marc.title_main": "Batch Processor \uD83D\uDCDA \u2192 \uD83D\uDCC4",
      "marc.title_sub": "Converter of Images into MARC Text",
      "marc.subtitle": "Batch processing tool for converting images to MARC text",
      "marc.api_key_label": "API Key:",
      "marc.system_prompt_label": "System Prompt:",
      "marc.load_prompt_button": "Load from static/prompts/marc.txt",
      "marc.username_label": "Username:",
      "marc.username_placeholder": "e.g. rek_user",
      "marc.custom_footer_label": "Custom Footer:",
      "marc.custom_footer_placeholder": "Optional text appended after each successful LLM response",
      "marc.choose_model_label": "Choose Model:",
      "marc.custom_model_label": "Or enter custom model ID:",
      "marc.custom_model_placeholder": "e.g. openai/gpt-4.1-mini",
      "marc.upload_zip_label": "Upload ZIP (optional if choosing a folder below):",
      "marc.choose_subfolder_prefix": "Or choose a subfolder from",
      "marc.no_folders_prefix": "No folders found in",
      "marc.include_inputs": "Include inputs in output zip",
      "marc.separate_outputs": "Separate text files in output zip",
      "marc.include_metadata": "Include metadata.json",
      "marc.save_concat_prefix": "Save concatenated results to",
      "marc.submit_job": "Submit Job",
      "marc.jobs_archive": "Jobs archive",
      "marc.prompt_load_error": "Failed to load prompt from static/prompts/marc.txt.",
      "status.selected_zip": "Selected existing ZIP: {name}",
      "status.selected_folder": "Selected folder: {name}/",
      "marc.item_singular": "item",
      "marc.item_plural": "items",
      "marc.folder_meta": "{count} {item_label} | {modified_at}",
      "marc.model_default_suffix": "(default)"
    },
    lv: {
      "language.label": "Valoda:",
      "language.english": "English",
      "language.latvian": "Latvie\u0161u",
      "marc.title_main": "Pake\u0161u apstr\u0101d\u0101t\u0101js \uD83D\uDCDA \u2192 \uD83D\uDCC4",
      "marc.title_sub": "Att\u0113lu p\u0101rveidot\u0101js MARC tekst\u0101",
      "marc.subtitle": "Masveida apstr\u0101des r\u012bks att\u0113lu p\u0101rveido\u0161anai MARC tekst\u0101",
      "marc.api_key_label": "API atsl\u0113ga:",
      "marc.system_prompt_label": "Sist\u0113mas uzvedne:",
      "marc.load_prompt_button": "Iel\u0101d\u0113t no static/prompts/marc.txt",
      "marc.username_label": "Lietot\u0101jv\u0101rds:",
      "marc.username_placeholder": "piem., rek_user",
      "marc.custom_footer_label": "Piel\u0101gots nobeigums:",
      "marc.custom_footer_placeholder": "Izv\u0113les teksts, kas tiek pievienots p\u0113c katras veiksm\u012bgas LLM atbildes",
      "marc.choose_model_label": "Izv\u0113lieties modeli:",
      "marc.custom_model_label": "Vai ievadiet piel\u0101gotu mode\u013ca ID:",
      "marc.custom_model_placeholder": "piem., openai/gpt-4.1-mini",
      "marc.upload_zip_label": "Aug\u0161upiel\u0101d\u0113t ZIP (nav oblig\u0101ti, ja zem\u0101k izv\u0113laties mapi):",
      "marc.choose_subfolder_prefix": "Vai izv\u0113lieties apak\u0161mapi no",
      "marc.no_folders_prefix": "Mapes nav atrastas \u0161eit",
      "marc.include_inputs": "Iek\u013caut ievades failus rezult\u0101tu zip arh\u012bv\u0101",
      "marc.separate_outputs": "Atdal\u012bt teksta failus rezult\u0101tu zip arh\u012bv\u0101",
      "marc.include_metadata": "Iek\u013caut metadata.json",
      "marc.save_concat_prefix": "Saglab\u0101t apvienotos rezult\u0101tus \u0161eit",
      "marc.submit_job": "Iesniegt darbu",
      "marc.jobs_archive": "Darbu arh\u012bvs",
      "marc.prompt_load_error": "Neizdev\u0101s iel\u0101d\u0113t uzvedni no static/prompts/marc.txt.",
      "status.selected_zip": "Izv\u0113l\u0113ts eso\u0161s ZIP: {name}",
      "status.selected_folder": "Izv\u0113l\u0113ta mape: {name}/",
      "marc.item_singular": "vien\u012bba",
      "marc.item_plural": "vien\u012bbas",
      "marc.folder_meta": "{count} {item_label} | {modified_at}",
      "marc.model_default_suffix": "(noklus\u0113jums)"
    }
  };

  let currentLanguage = DEFAULT_LANGUAGE;

  const safeGetLocalStorage = (key) => {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  };

  const safeSetLocalStorage = (key, value) => {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // Ignore storage write failures and continue with in-memory language.
    }
  };

  const normalizeLanguage = (value) => (SUPPORTED.includes(value) ? value : DEFAULT_LANGUAGE);

  const readLanguage = () => normalizeLanguage(safeGetLocalStorage(STORAGE_KEY) || DEFAULT_LANGUAGE);

  const interpolate = (template, vars) =>
    String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, variableName) => {
      if (!vars || vars[variableName] === undefined || vars[variableName] === null) {
        return match;
      }
      return String(vars[variableName]);
    });

  const getTemplate = (key) => {
    const inCurrent = translations[currentLanguage] && translations[currentLanguage][key];
    if (inCurrent !== undefined) {
      return inCurrent;
    }
    const inDefault = translations[DEFAULT_LANGUAGE] && translations[DEFAULT_LANGUAGE][key];
    if (inDefault !== undefined) {
      return inDefault;
    }
    return key;
  };

  const t = (key, vars = {}) => interpolate(getTemplate(key), vars);

  const applyTextTranslations = () => {
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const key = element.dataset.i18n;
      if (!key) {
        return;
      }
      element.textContent = t(key);
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      const key = element.dataset.i18nPlaceholder;
      if (!key || !("placeholder" in element)) {
        return;
      }
      element.placeholder = t(key);
    });

    document.querySelectorAll("[data-i18n-value]").forEach((element) => {
      const key = element.dataset.i18nValue;
      if (!key || !("value" in element)) {
        return;
      }
      element.value = t(key);
    });
  };

  const applyFolderMetaTranslations = () => {
    document.querySelectorAll("[data-item-count][data-modified-at]").forEach((element) => {
      const countText = (element.dataset.itemCount || "").trim();
      const countValue = Number.parseInt(countText, 10);
      const count = Number.isFinite(countValue) ? countValue : 0;
      const modifiedAt = element.dataset.modifiedAt || "";
      const itemLabel = count === 1 ? t("marc.item_singular") : t("marc.item_plural");
      element.textContent = t("marc.folder_meta", {
        count,
        item_label: itemLabel,
        modified_at: modifiedAt
      });
    });
  };

  const applyModelDefaultSuffix = () => {
    const defaultModelOption = document.querySelector(
      'select[name="model_dropdown"] option[value="google/gemini-3-flash-preview"]'
    );
    if (!defaultModelOption) {
      return;
    }

    if (!defaultModelOption.dataset.modelBaseLabel) {
      defaultModelOption.dataset.modelBaseLabel = defaultModelOption.textContent
        .replace(/\s*\([^)]*\)\s*$/, "")
        .trim();
    }

    defaultModelOption.textContent = `${defaultModelOption.dataset.modelBaseLabel} ${t("marc.model_default_suffix")}`;
  };

  const updateToggleState = () => {
    const buttons = Array.from(document.querySelectorAll(".language-toggle-button[data-lang]"));
    buttons.forEach((button) => {
      const isActive = button.dataset.lang === currentLanguage;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
  };

  const applyAllTranslations = () => {
    applyTextTranslations();
    applyFolderMetaTranslations();
    applyModelDefaultSuffix();
  };

  const setLanguage = (languageCode) => {
    currentLanguage = normalizeLanguage(languageCode);
    safeSetLocalStorage(STORAGE_KEY, currentLanguage);
    applyAllTranslations();
    updateToggleState();
    document.dispatchEvent(
      new CustomEvent("marc-language-change", { detail: { language: currentLanguage } })
    );
  };

  const getLanguage = () => currentLanguage;

  const initToggleHandlers = () => {
    const buttons = Array.from(document.querySelectorAll(".language-toggle-button[data-lang]"));
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        setLanguage(button.dataset.lang);
      });
    });
  };

  const init = () => {
    currentLanguage = readLanguage();
    window.formCacheI18n = { t, getLanguage };
    initToggleHandlers();
    applyAllTranslations();
    updateToggleState();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
