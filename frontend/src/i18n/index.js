/* i18next setup (Feature 14): English, French, Swahili.
 * Browser language auto-detected on first visit; choice stored in localStorage.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./en.json";
import fr from "./fr.json";
import sw from "./sw.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { t: en }, fr: { t: fr }, sw: { t: sw } },
    ns: ["t"], defaultNS: "t",
    fallbackLng: "en",
    supportedLngs: ["en", "fr", "sw"],
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "cropwatch_lang",
      caches: ["localStorage"],
    },
  });

export default i18n;
