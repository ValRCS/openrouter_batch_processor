(() => {
  const STORAGE_KEY = "marc_ui_language";
  const SUPPORTED = ["en", "lv"];
  const DEFAULT_LANGUAGE = "en";

  const translations = {
    en: {
      "language.label": "Language:",
      "language.english": "English",
      "language.latvian": "Latviešu",
      "marc.title_main": "Batch Processor 📚 → 📄",
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
      "language.latvian": "Latviešu",
      "marc.title_main": "Pakešu apstrādātājs 📚 → 📄",
      "marc.title_sub": "Attēlu pārveidotājs MARC tekstā",
      "marc.subtitle": "Masveida apstrādes rīks attēlu pārveidošanai MARC tekstā",
      "marc.api_key_label": "API atslēga:",
      "marc.system_prompt_label": "Sistēmas uzvedne:",
      "marc.load_prompt_button": "Ielādēt no static/prompts/marc.txt",
      "marc.username_label": "Lietotājvārds:",
      "marc.username_placeholder": "piem., rek_user",
      "marc.custom_footer_label": "Pielāgots nobeigums:",
      "marc.custom_footer_placeholder": "Izvēles teksts, kas tiek pievienots pēc katras veiksmīgas LLM atbildes",
      "marc.choose_model_label": "Izvēlieties modeli:",
      "marc.custom_model_label": "Vai ievadiet pielāgotu modeļa ID:",
      "marc.custom_model_placeholder": "piem., openai/gpt-4.1-mini",
      "marc.upload_zip_label": "Augšupielādēt ZIP (nav obligāti, ja zemāk izvēlaties mapi):",
      "marc.choose_subfolder_prefix": "Vai izvēlieties apakšmapi no",
      "marc.no_folders_prefix": "Mapes nav atrastas šeit",
      "marc.include_inputs": "Iekļaut ievades failus rezultātu zip arhīvā",
      "marc.separate_outputs": "Atdalīt teksta failus rezultātu zip arhīvā",
      "marc.include_metadata": "Iekļaut metadata.json",
      "marc.save_concat_prefix": "Saglabāt apvienotos rezultātus šeit",
      "marc.submit_job": "Iesniegt darbu",
      "marc.jobs_archive": "Darbu arhīvs",
      "marc.prompt_load_error": "Neizdevās ielādēt uzvedni no static/prompts/marc.txt.",
      "status.selected_zip": "Izvēlēts esošs ZIP: {name}",
      "status.selected_folder": "Izvēlēta mape: {name}/",
      "marc.item_singular": "vienība",
      "marc.item_plural": "vienības",
      "marc.folder_meta": "{count} {item_label} | {modified_at}",
      "marc.model_default_suffix": "(noklusējums)"
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
