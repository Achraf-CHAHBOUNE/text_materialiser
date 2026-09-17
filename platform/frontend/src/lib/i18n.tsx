/**
 * Arabic / French, the two languages Moroccan legal work is done in.
 *
 * Arabic is the default: the rulings themselves are Arabic. Switching language
 * flips the whole page direction (Arabic reads right to left) and the chamber
 * and city names. Digits stay Latin in both: Morocco writes Arabic with 0-9,
 * and a ruling's number is part of its identity anyway. The ruling's own text
 * is never translated: it is the court's wording and must stay as written.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "ar" | "fr";
const STORAGE_KEY = "anon-lang";

type Entry = { ar: string; fr: string };

const STRINGS = {
  // shell / navigation
  "nav.browse": { ar: "الاجتهادات", fr: "Jurisprudence" },
  "nav.dashboard": { ar: "لوحة القيادة", fr: "Tableau de bord" },
  "nav.decisions": { ar: "القرارات", fr: "Décisions" },
  "nav.admin": { ar: "الإدارة", fr: "Administration" },
  "nav.signOut": { ar: "تسجيل الخروج", fr: "Se déconnecter" },
  "lang.switch": { ar: "Français", fr: "العربية" },

  // login
  "login.title": { ar: "تسجيل الدخول إلى فضائك", fr: "Connexion à votre espace" },
  "login.subtitle": {
    ar: "الاطلاع على الاجتهادات القضائية بعد إزالة البيانات الشخصية.",
    fr: "Consultez la jurisprudence, données personnelles supprimées.",
  },
  "login.email": { ar: "البريد الإلكتروني", fr: "Adresse e-mail" },
  "login.password": { ar: "كلمة المرور", fr: "Mot de passe" },
  "login.submit": { ar: "دخول", fr: "Se connecter" },
  "login.busy": { ar: "جارٍ الدخول…", fr: "Connexion…" },
  "login.failed": { ar: "تعذّر تسجيل الدخول", fr: "Échec de la connexion" },
  "login.welcome": { ar: "أهلاً بعودتك", fr: "Bon retour" },
  "login.preview": { ar: "معاينة النص المجهول", fr: "Aperçu du texte anonymisé" },
  "login.signedOut": { ar: "تم تسجيل الخروج", fr: "Déconnecté" },

  // shell
  "shell.home": { ar: "الرئيسية", fr: "Accueil" },
  "shell.nav": { ar: "التنقل", fr: "Navigation" },
  "shell.openNav": { ar: "فتح القائمة", fr: "Ouvrir le menu" },
  "shell.collapse": { ar: "طيّ القائمة", fr: "Replier le menu" },
  "shell.expand": { ar: "توسيع القائمة", fr: "Déplier le menu" },
  "shell.accountMenu": { ar: "قائمة الحساب", fr: "Menu du compte" },
  "shell.profile": { ar: "الملف الشخصي", fr: "Profil" },
  "shell.theme.light": { ar: "الوضع الفاتح", fr: "Thème clair" },
  "shell.theme.dark": { ar: "الوضع الداكن", fr: "Thème sombre" },

  // dashboard / decisions
  "dash.title": { ar: "لوحة القيادة", fr: "Tableau de bord" },
  "dash.overview": { ar: "نظرة عامة على المنصة", fr: "Vue d'ensemble de la plateforme" },
  "dash.forClient": { ar: "تصفّح القرارات بعد إزالة البيانات الشخصية", fr: "Consulter les décisions anonymisées" },
  "dash.decisions": { ar: "القرارات", fr: "Décisions" },
  "dash.published": { ar: "المنشورة", fr: "Publiées" },
  "dash.pending": { ar: "في انتظار المراجعة", fr: "En attente de revue" },
  "dash.clients": { ar: "العملاء", fr: "Clients" },
  "dash.integration": { ar: "الاستيراد", fr: "Intégration" },
  "results.title": { ar: "القرارات", fr: "Décisions" },
  "results.subtitle": {
    ar: "ابحث في القرارات المنشورة بعد إزالة البيانات الشخصية",
    fr: "Rechercher parmi les décisions anonymisées publiées",
  },
  "results.search": { ar: "بحث في القرارات…", fr: "Rechercher une décision…" },
  "results.filterChamber": { ar: "تصفية حسب الغرفة", fr: "Filtrer par chambre" },
  "results.filterLevel": { ar: "تصفية حسب الدرجة", fr: "Filtrer par degré" },
  "results.allChambers": { ar: "كل الغرف", fr: "Toutes les chambres" },
  "results.allLevels": { ar: "كل الدرجات", fr: "Tous les degrés" },

  // browse: menu
  "browse.title": { ar: "الاجتهادات القضائية", fr: "Jurisprudence" },
  "browse.subtitle": {
    ar: "محكمة النقض · المحكمة الدستورية · محاكم الاستئناف",
    fr: "Cour de cassation · Cour constitutionnelle · Cours d'appel",
  },
  "browse.searchAll": { ar: "البحث في نص القرارات…", fr: "Rechercher dans le texte des arrêts…" },
  "browse.available": { ar: "قرار متاح للاطلاع", fr: "arrêts consultables" },
  "browse.empty": { ar: "لا توجد قرارات منشورة بعد.", fr: "Aucun arrêt publié pour le moment." },
  "browse.loadError": {
    ar: "تعذّر تحميل القائمة. حدّث الصفحة أو أعد تسجيل الدخول.",
    fr: "Chargement impossible. Actualisez la page ou reconnectez-vous.",
  },
  "browse.rulingsCount": { ar: "قرار", fr: "arrêts" },

  "court.cassation": { ar: "محكمة النقض", fr: "Cour de cassation" },

  // browse: chamber listing
  "listing.allChambers": { ar: "كل الغرف", fr: "Toutes les chambres" },
  "listing.allYears": { ar: "كل السنوات", fr: "Toutes les années" },
  "listing.search": {
    ar: "ابحث برقم القرار أو بكلمة من نصه…",
    fr: "Rechercher par numéro d'arrêt ou par mot…",
  },
  "listing.filters": { ar: "التصفية:", fr: "Filtres :" },
  "listing.filterSearch": { ar: "بحث", fr: "Recherche" },
  "listing.filterYear": { ar: "السنة", fr: "Année" },
  "listing.filterCity": { ar: "المدينة", fr: "Ville" },
  "listing.clear": { ar: "إزالة", fr: "Retirer" },
  "listing.none": { ar: "لا توجد قرارات مطابقة.", fr: "Aucun arrêt correspondant." },
  "listing.city": { ar: "المدينة", fr: "Ville" },
  "listing.all": { ar: "الكل", fr: "Toutes" },
  "listing.prev": { ar: "السابق", fr: "Précédent" },
  "listing.next": { ar: "التالي", fr: "Suivant" },
  "listing.page": { ar: "صفحة", fr: "Page" },
  "listing.of": { ar: "من", fr: "sur" },
  "listing.first": { ar: "الأولى", fr: "Première" },
  "listing.last": { ar: "الأخيرة", fr: "Dernière" },
  "listing.perPage": { ar: "لكل صفحة", fr: "par page" },
  "listing.showing": { ar: "عرض", fr: "Affichage" },
  "listing.to": { ar: "إلى", fr: "à" },
  "listing.results": { ar: "من أصل", fr: "sur" },
  "listing.open": { ar: "فتح القرار", fr: "Ouvrir l'arrêt" },

  // table headers
  "col.number": { ar: "رقم القرار", fr: "N° de l'arrêt" },
  "col.date": { ar: "تاريخ القرار", fr: "Date de l'arrêt" },
  "col.city": { ar: "المدينة", fr: "Ville" },
  "col.chamber": { ar: "الغرفة", fr: "Chambre" },
  "col.fileNo": { ar: "رقم الملف", fr: "N° du dossier" },

  // ruling page
  "ruling.download": { ar: "تحميل الملف", fr: "Télécharger" },
  "ruling.print": { ar: "طباعة", fr: "Imprimer" },
  "ruling.noText": { ar: "لا يوجد نص متاح.", fr: "Texte non disponible." },
  "ruling.notice": {
    ar: "أُزيلت البيانات الشخصية من هذا القرار آليًا وعُوّضت بالرمز XXXXXXX.",
    fr: "Les données personnelles de cet arrêt ont été supprimées automatiquement et remplacées par XXXXXXX.",
  },
  "ruling.error": {
    ar: "تعذّر فتح القرار. قد يكون غير منشور.",
    fr: "Impossible d'ouvrir l'arrêt. Il n'est peut-être pas publié.",
  },
  "ruling.decisionOf": { ar: "قرار عدد", fr: "Arrêt n°" },
  "ruling.noDate": { ar: "بدون تاريخ", fr: "Sans date" },

  // editing a ruling
  "edit.hide": { ar: "إخفاء", fr: "Masquer" },
  "edit.hideAll": { ar: "إخفاء في كل النص", fr: "Masquer partout" },
  "edit.editText": { ar: "تعديل النص", fr: "Modifier le texte" },
  "edit.editDetails": { ar: "تعديل البيانات", fr: "Modifier les informations" },
  "edit.save": { ar: "حفظ", fr: "Enregistrer" },
  "edit.cancel": { ar: "إلغاء", fr: "Annuler" },
  "edit.review": { ar: "مراجعة التغييرات", fr: "Vérifier les modifications" },
  "edit.back": { ar: "رجوع إلى التعديل", fr: "Revenir à l'édition" },
  "edit.goesLive": {
    ar: "هذا التغيير يحذف نصًا فقط، لذا يُنشر فورًا.",
    fr: "Cette modification ne fait que retirer du texte : elle est publiée immédiatement.",
  },
  "edit.needsApproval": {
    ar: "هذا التغيير يضيف نصًا، وقد يُظهر اسمًا. يُحفظ كمسودة ولا يُنشر إلا بعد الموافقة.",
    fr: "Cette modification ajoute du texte et pourrait réafficher un nom : elle est enregistrée en brouillon et publiée seulement après approbation.",
  },
  "edit.saveLive": { ar: "حفظ ونشر", fr: "Enregistrer et publier" },
  "edit.saveDraft": { ar: "حفظ كمسودة", fr: "Enregistrer en brouillon" },
  "edit.noChange": { ar: "لم تغيّر شيئًا بعد.", fr: "Aucune modification pour l'instant." },
  "edit.hidden": { ar: "تم الإخفاء — النسخة", fr: "Masqué — version" },
  "edit.draftSaved": {
    ar: "حُفظت المسودة، وهي في انتظار الموافقة.",
    fr: "Brouillon enregistré, en attente d'approbation.",
  },
  "edit.hideAllTitle": { ar: "إخفاء في كل النص؟", fr: "Masquer partout ?" },
  "edit.occurrences": { ar: "موضع سيُخفى", fr: "occurrence(s) seront masquées" },
  "edit.hideAllConfirm": { ar: "إخفاء الكل", fr: "Tout masquer" },
  "edit.hideAllNote": {
    ar: "كلمات كاملة فقط، مع مراعاة اختلاف الهمزات والتشكيل.",
    fr: "Mots entiers uniquement, en tolérant les variantes de hamza et les diacritiques.",
  },
  "edit.none": { ar: "لم يُعثر عليه في النص.", fr: "Introuvable dans le texte." },
  "edit.selectHint": {
    ar: "حدّد اسمًا في النص لإخفائه.",
    fr: "Sélectionnez un nom dans le texte pour le masquer.",
  },
  "edit.conflict": {
    ar: "تغيّر هذا القرار في الأثناء. أُعيد تحميله، أعد التعديل.",
    fr: "Cet arrêt a été modifié entre-temps. Il a été rechargé : refaites la modification.",
  },
  "edit.gate": { ar: "رُفض: عُثر على بيانات شخصية", fr: "Refusé : données personnelles détectées" },
  "edit.edited": { ar: "معدَّل يدويًا", fr: "Modifié manuellement" },
  "edit.saved": { ar: "حُفظت البيانات", fr: "Informations enregistrées" },
  "edit.line": { ar: "السطر", fr: "Ligne" },

  "history.title": { ar: "سجل التعديلات", fr: "Historique" },
  "history.current": { ar: "الحالية", fr: "Actuelle" },
  "history.restore": { ar: "استرجاع", fr: "Restaurer" },
  "history.restoreTitle": { ar: "استرجاع النسخة", fr: "Restaurer la version" },
  "history.purge": { ar: "حذف النسخ السابقة", fr: "Supprimer les anciennes versions" },
  "history.purgeBody": {
    ar: "النسخ السابقة تحتفظ بالنص كما كان قبل الإخفاء، بما فيه الأسماء المخفية. حذفها نهائي: لن يمكن الاسترجاع بعده.",
    fr: "Les anciennes versions gardent le texte d'avant le masquage, noms compris. La suppression est définitive : plus aucune restauration possible.",
  },
  "history.purged": { ar: "حُذفت النسخ السابقة", fr: "Anciennes versions supprimées" },
  "history.empty": { ar: "لم يُعدَّل هذا القرار بعد.", fr: "Cet arrêt n'a jamais été modifié." },
  "history.drafts": { ar: "مسودات في انتظار الموافقة", fr: "Brouillons à approuver" },
  "history.approve": { ar: "موافقة ونشر", fr: "Approuver et publier" },
  "history.discard": { ar: "رفض", fr: "Rejeter" },
  "history.open": { ar: "عرض", fr: "Voir" },
  "history.stale": {
    ar: "كُتبت هذه المسودة على نسخة أقدم. ارفضها ثم أعد التعديل.",
    fr: "Ce brouillon porte sur une version antérieure. Rejetez-le puis refaites la modification.",
  },
  "history.by": { ar: "بواسطة", fr: "par" },
  "history.hiddenCount": { ar: "موضع مخفي", fr: "masqué(s)" },
  "history.changeCount": { ar: "تغيير", fr: "modification(s)" },
  "history.reports": { ar: "بلاغات القراء", fr: "Signalements des lecteurs" },
  "history.resolve": { ar: "تمت المعالجة", fr: "Traité" },
  "history.dismiss": { ar: "تجاهل", fr: "Ignorer" },
  "history.action.import": { ar: "كما استُورد", fr: "Importé" },
  "history.action.hide": { ar: "إخفاء", fr: "Masquage" },
  "history.action.hide_all": { ar: "إخفاء في كل النص", fr: "Masquage partout" },
  "history.action.edit": { ar: "تعديل النص", fr: "Modification du texte" },
  "history.action.restore": { ar: "استرجاع", fr: "Restauration" },
  "history.action.title": { ar: "تغيير العنوان", fr: "Changement de titre" },
  "history.action.replace_file": { ar: "استبدال الملف", fr: "Remplacement du fichier" },

  "report.title": { ar: "الإبلاغ عن مشكل", fr: "Signaler un problème" },
  "report.hint": {
    ar: "مثلًا اسم شخص ما زال ظاهرًا. سيراجعه مسؤول.",
    fr: "Par exemple un nom encore visible. Un administrateur le vérifiera.",
  },
  "report.quote": { ar: "النص المحدد", fr: "Texte sélectionné" },
  "report.note": { ar: "ملاحظة", fr: "Remarque" },
  "report.send": { ar: "إرسال", fr: "Envoyer" },
  "report.sent": { ar: "شكرًا، وصل البلاغ.", fr: "Merci, signalement envoyé." },

  "nav.review": { ar: "التصحيحات", fr: "Corrections" },
  "review.subtitle": {
    ar: "بلاغات القراء والمسودات في انتظار الموافقة",
    fr: "Signalements des lecteurs et brouillons en attente",
  },
  "review.export": { ar: "تصدير القرارات المعدَّلة", fr: "Exporter les arrêts modifiés" },
  "review.exportHint": {
    ar: "لإدراج التصحيحات في مجلد النتائج المسلَّم للعميل:",
    fr: "Pour intégrer les corrections au dossier de résultats livré au client :",
  },
  "review.noReports": { ar: "لا توجد بلاغات مفتوحة.", fr: "Aucun signalement ouvert." },
  "review.noDrafts": { ar: "لا توجد مسودات.", fr: "Aucun brouillon." },
} satisfies Record<string, Entry>;

export type StringKey = keyof typeof STRINGS;

const CHAMBERS: Record<string, Entry> = {
  "أحوال شخصية": { ar: "غرفة الأحوال الشخصية", fr: "Chambre du statut personnel" },
  "تجارية": { ar: "الغرفة التجارية", fr: "Chambre commerciale" },
  "اجتماعية": { ar: "الغرفة الاجتماعية", fr: "Chambre sociale" },
  "عقارية": { ar: "الغرفة العقارية", fr: "Chambre foncière" },
  "جنائية": { ar: "الغرفة الجنائية", fr: "Chambre pénale" },
  "مدنية": { ar: "الغرفة المدنية", fr: "Chambre civile" },
  "إدارية": { ar: "الغرفة الإدارية", fr: "Chambre administrative" },
  "غير محدد": { ar: "غير محدد", fr: "Non déterminée" },
};

const COURTS: Record<string, Entry> = {
  "محكمة النقض": { ar: "محكمة النقض", fr: "Cour de cassation" },
  "محكمة الاستئناف": { ar: "محكمة الاستئناف", fr: "Cour d'appel" },
  "المحكمة الابتدائية": { ar: "المحكمة الابتدائية", fr: "Tribunal de première instance" },
  "المحكمة الدستورية": { ar: "المحكمة الدستورية", fr: "Cour constitutionnelle" },
  "المجلس الأعلى للحسابات": { ar: "المجلس الأعلى للحسابات", fr: "Cour des comptes" },
};

/** Court seats, in the spelling each language uses. */
const CITIES: Record<string, string> = {
  "الرباط": "Rabat", "الدار البيضاء": "Casablanca", "فاس": "Fès", "مكناس": "Meknès",
  "مراكش": "Marrakech", "أكادير": "Agadir", "طنجة": "Tanger", "تطوان": "Tétouan",
  "وجدة": "Oujda", "القنيطرة": "Kénitra", "الجديدة": "El Jadida", "سطات": "Settat",
  "بني ملال": "Béni Mellal", "خريبكة": "Khouribga", "آسفي": "Safi", "ورزازات": "Ouarzazate",
  "الرشيدية": "Errachidia", "تازة": "Taza", "الحسيمة": "Al Hoceïma", "الناظور": "Nador",
  "العيون": "Laâyoune", "كلميم": "Guelmim", "العرائش": "Larache", "سلا": "Salé",
  "تمارة": "Témara", "الخميسات": "Khémisset", "المحمدية": "Mohammédia",
  "بن سليمان": "Benslimane", "برشيد": "Berrechid", "سيدي بنور": "Sidi Bennour",
  "اليوسفية": "Youssoufia", "الصويرة": "Essaouira", "شيشاوة": "Chichaoua",
  "قلعة السراغنة": "Kelaa des Sraghna", "ابن جرير": "Benguerir", "إنزكان": "Inezgane",
  "تارودانت": "Taroudant", "تزنيت": "Tiznit", "طاطا": "Tata", "طانطان": "Tan-Tan",
  "السمارة": "Smara", "الداخلة": "Dakhla", "بوجدور": "Boujdour", "صفرو": "Sefrou",
  "بولمان": "Boulemane", "تاونات": "Taounate", "الحاجب": "El Hajeb", "إفران": "Ifrane",
  "ميدلت": "Midelt", "خنيفرة": "Khénifra", "أزرو": "Azrou",
  "الفقيه بن صالح": "Fquih Ben Salah", "قصبة تادلة": "Kasba Tadla", "أزيلال": "Azilal",
  "وادي زم": "Oued Zem", "أبي الجعد": "Abi Jaad", "زاكورة": "Zagora", "تنغير": "Tinghir",
  "بوعرفة": "Bouarfa", "فجيج": "Figuig", "جرادة": "Jerada", "تاوريرت": "Taourirt",
  "بركان": "Berkane", "الدريوش": "Driouch", "القصر الكبير": "Ksar El Kébir",
  "أصيلة": "Asilah", "شفشاون": "Chefchaouen", "وزان": "Ouezzane", "سيدي قاسم": "Sidi Kacem",
  "سيدي سليمان": "Sidi Slimane", "سوق أربعاء الغرب": "Souk El Arbaa", "تيفلت": "Tiflet",
  "الرماني": "Rommani", "سيدي إفني": "Sidi Ifni", "الصخيرات": "Skhirat", "جرسيف": "Guercif",
};

type Ctx = {
  lang: Lang;
  dir: "rtl" | "ltr";
  setLang: (l: Lang) => void;
  /** a UI string */
  t: (key: StringKey) => string;
  /** a chamber, as the language names it */
  chamber: (value: string) => string;
  court: (value: string) => string;
  city: (value: string) => string;
  /** a number as the reader expects to see it */
  num: (value: number | string) => string;
};

const LanguageContext = createContext<Ctx | null>(null);

// Morocco writes Arabic with Latin digits -- a ruling numbered 90 is "90" on the
// court's own paper, not "٩٠". Only counts are grouped; a decision number, a
// file number and a date are passed through exactly as the court wrote them.
const asRead = (v: number | string) =>
  typeof v === "number" ? v.toLocaleString("en-US") : String(v);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ar");

  // Read the saved choice after mount: the server render has no localStorage,
  // and reading it during render would make the two disagree.
  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "fr" || saved === "ar") setLangState(saved);
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* private browsing: the choice just does not persist */
    }
  }, []);

  const dir = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const value = useMemo<Ctx>(() => ({
    lang,
    dir,
    setLang,
    t: (key) => STRINGS[key][lang],
    chamber: (v) => CHAMBERS[v]?.[lang] ?? v,
    court: (v) => COURTS[v]?.[lang] ?? v,
    city: (v) => (lang === "fr" ? (CITIES[v] ?? v) : v),
    num: asRead,
  }), [lang, dir, setLang]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useI18n must be used inside <LanguageProvider>");
  return ctx;
}
