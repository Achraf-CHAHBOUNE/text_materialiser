/**
 * Arabic / French, the two languages Moroccan legal work is done in.
 *
 * Arabic is the default: the rulings themselves are Arabic. Switching language
 * flips the whole page direction (Arabic reads right to left) and the chamber
 * and city names. Digits stay Latin in both: Morocco writes Arabic with 0-9,
 * and a ruling's number is part of its identity anyway. The ruling's own text
 * is never translated: it is the court's wording and must stay as written.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useRouter, useRouterState } from "@tanstack/react-router";
import { STORAGE_KEY, getActiveLang, langFromPath, setActiveLang, swapLang, type Lang } from "./lang-url";

export type { Lang } from "./lang-url";

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
  // The Cassation portal heads this column "المفاتيح أو القاعدة أو المحتوى": whichever
  // of the three the ruling offers is what gets shown.
  "col.keys": { ar: "المفاتيح أو القاعدة أو المحتوى", fr: "Mots-clés, principe ou contenu" },
  "listing.allThemes": { ar: "كل المواضيع", fr: "Tous les sujets" },
  "listing.noMatch": { ar: "لا يوجد ما يطابق البحث", fr: "Aucun résultat" },
  "listing.findTheme": { ar: "ابحث عن موضوع...", fr: "Chercher un sujet..." },
  "listing.findCity": { ar: "ابحث عن مدينة...", fr: "Chercher une ville..." },
  "listing.findYear": { ar: "ابحث عن سنة...", fr: "Chercher une année..." },
  "listing.theme": { ar: "الموضوع", fr: "Sujet" },
  "listing.filterTheme": { ar: "الموضوع", fr: "Sujet" },
  "listing.noTheme": { ar: "بدون موضوع مدون", fr: "Aucun sujet imprimé" },
  "listing.themeNote": {
    ar: "المواضيع مأخوذة من الكلمات التي دونتها المحكمة على القرار نفسه.",
    fr: "Les sujets proviennent des mots que la Cour a imprimés sur l'arrêt lui-même.",
  },
  "col.fileNo": { ar: "رقم الملف", fr: "N° du dossier" },

  // ruling page
  "ruling.headnote": { ar: "موضوع القرار وقاعدته", fr: "Sujet et principe de l'arrêt" },
  "ruling.keywords": { ar: "المفاتيح", fr: "Mots-clés" },
  "ruling.rule": { ar: "القاعدة", fr: "Principe" },
  "ruling.abstract": { ar: "ملخص", fr: "Résumé" },
  "source.court": { ar: "من نص القرار", fr: "Tiré de l'arrêt" },
  "source.model": { ar: "تحرير آلي", fr: "Rédigé automatiquement" },
  "ruling.abstractNote": {
    ar: "هذا الملخص والموضوع حُرّرا آليًا انطلاقًا من نص القرار، ولم تدوّنهما المحكمة.",
    fr: "Ce résumé et ce sujet ont été rédigés automatiquement à partir de l'arrêt; ils ne figurent pas sur celui-ci.",
  },
  "ruling.headnoteNote": {
    ar: "هذه الكلمات والقاعدة مدونة في القرار نفسه كما حررتها المحكمة.",
    fr: "Ces mots-clés et ce principe figurent sur l'arrêt, tels que rédigés par la Cour.",
  },
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

  // reading it in French
  "tr.button": { ar: "الترجمة الفرنسية", fr: "Traduction française" },
  "tr.hide": { ar: "إخفاء الترجمة", fr: "Masquer la traduction" },
  "tr.working": { ar: "جارٍ الترجمة…", fr: "Traduction en cours…" },
  "tr.wait": {
    ar: "تُترجَم هذه المرة فقط؛ بعدها تظهر فورًا لكل القرّاء.",
    fr: "La traduction n'est faite qu'une fois ; ensuite elle s'affiche immédiatement pour tous.",
  },
  "tr.original": { ar: "النص الأصلي (عربي)", fr: "Texte original (arabe)" },
  "tr.french": { ar: "الترجمة (فرنسية)", fr: "Traduction (français)" },
  "tr.notice": {
    ar: "ترجمة آلية للاطّلاع فقط. النص العربي هو الأصل وهو المعتمد قانونًا.",
    fr: "Traduction automatique, fournie à titre indicatif. Seul le texte arabe fait foi.",
  },
  "tr.stale": {
    ar: "عُدِّل هذا القرار بعد ترجمته. اطلب ترجمة جديدة.",
    fr: "Cet arrêt a été corrigé après sa traduction. Demandez une nouvelle traduction.",
  },
  "tr.retry": { ar: "إعادة الترجمة", fr: "Retraduire" },
  "tr.failed": { ar: "تعذّرت الترجمة", fr: "La traduction a échoué" },

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


  // the French site
  "fr.ruleTranslated": { ar: "ترجمة آلية لقاعدة المحكمة", fr: "Traduction automatique de la règle de la Cour" },
  "fr.machineSummary": { ar: "ملخص آلي مترجم", fr: "Résumé automatique traduit" },
  "fr.notTranslated": { ar: "غير مترجم بعد", fr: "Pas encore traduit — texte arabe" },
  "fr.textMissing": {
    ar: "لا توجد ترجمة لهذا القرار بعد. يُعرض النص العربي.",
    fr: "Traduction non disponible pour cet arrêt. Le texte arabe est affiché.",
  },
  "fr.viewLabel": { ar: "طريقة العرض", fr: "Affichage" },
  "fr.viewFr": { ar: "الفرنسية", fr: "Français" },
  "fr.viewAr": { ar: "الأصل العربي", fr: "Original arabe" },
  "fr.viewBoth": { ar: "جنبًا إلى جنب", fr: "Côte à côte" },
  "fr.headnoteNote": {
    ar: "ترجمة آلية. النص العربي هو المرجع.",
    fr: "Traduction automatique. Seul le texte arabe fait foi.",
  },

  // decisions list (results)
  "results.none": { ar: "لا نتائج مطابقة", fr: "Aucun résultat" },
  "results.noneYet": { ar: "لا قرارات منشورة بعد", fr: "Aucune décision publiée pour l'instant" },
  "col.level": { ar: "المستوى", fr: "Niveau" },


  // dashboard
  "dash.adminHint": {
    ar: "استيراد دفعة من المعالجة، ومراجعة القائمة، ونشر القرارات، وإدارة حسابات العملاء.",
    fr: "Importer un lot du pipeline, traiter la file de révision, publier les décisions et gérer les comptes clients.",
  },
  "dash.openAdmin": { ar: "فتح لوحة الإدارة", fr: "Ouvrir la console d'administration" },
  "dash.signedInAs": { ar: "متصل باسم", fr: "Connecté en tant que" },
  "dash.byChamber": { ar: "تصفح القرارات المنشورة حسب الغرفة.", fr: "Parcourez les décisions publiées par chambre." },
  "dash.browseAll": { ar: "تصفح كل القرارات", fr: "Parcourir toutes les décisions" },

  // the business side: accounts, CRM, billing, support, library
  "nav.account": { ar: "حسابي", fr: "Mon compte" },
  "nav.alerts": { ar: "تنبيهاتي", fr: "Mes alertes" },
  "nav.crm": { ar: "إدارة العملاء", fr: "CRM" },
  "nav.history": { ar: "السجل", fr: "Historique" },
  "nav.library": { ar: "ملفاتي", fr: "Mes dossiers" },
  "nav.support": { ar: "الدعم", fr: "Assistance" },
  "role.admin": { ar: "مسؤول", fr: "Administrateur" },
  "role.editor": { ar: "محرر", fr: "Éditeur" },
  "role.sales": { ar: "مبيعات", fr: "Commercial" },
  "role.client_admin": { ar: "صاحب الحساب", fr: "Titulaire du compte" },
  "role.client": { ar: "قارئ", fr: "Lecteur" },
  "kind.firm": { ar: "مكتب محاماة", fr: "Cabinet" },
  "kind.company": { ar: "شركة", fr: "Entreprise" },
  "kind.institution": { ar: "مؤسسة", fr: "Institution" },
  "kind.individual": { ar: "فرد", fr: "Particulier" },
  "src.website": { ar: "الموقع", fr: "Site web" },
  "src.phone": { ar: "هاتف", fr: "Téléphone" },
  "src.event": { ar: "حدث", fr: "Événement" },
  "src.referral": { ar: "توصية", fr: "Recommandation" },
  "src.other": { ar: "آخر", fr: "Autre" },
  "act.call": { ar: "مكالمة", fr: "Appel" },
  "act.email": { ar: "بريد", fr: "E-mail" },
  "act.meeting": { ar: "لقاء", fr: "Rendez-vous" },
  "act.note": { ar: "ملاحظة", fr: "Note" },
  "pay.transfer": { ar: "تحويل", fr: "Virement" },
  "pay.cheque": { ar: "شيك", fr: "Chèque" },
  "pay.cash": { ar: "نقدا", fr: "Espèces" },
  "pay.card": { ar: "بطاقة", fr: "Carte" },
  "mail.queued": { ar: "في الانتظار", fr: "En attente" },
  "mail.sent": { ar: "أُرسل", fr: "Envoyé" },
  "mail.failed": { ar: "فشل", fr: "Échec" },
  "st.ok": { ar: "ساري", fr: "Actif" },
  "st.active": { ar: "نشط", fr: "Actif" },
  "st.paid": { ar: "مؤداة", fr: "Payée" },
  "st.won": { ar: "مكسوبة", fr: "Gagnée" },
  "st.customer": { ar: "عميل", fr: "Client" },
  "st.converted": { ar: "محوَّل", fr: "Converti" },
  "st.closed": { ar: "مغلق", fr: "Clos" },
  "st.trial": { ar: "تجربة", fr: "Essai" },
  "st.new": { ar: "جديد", fr: "Nouveau" },
  "st.open": { ar: "مفتوح", fr: "Ouvert" },
  "st.demo": { ar: "عرض تجريبي", fr: "Démo" },
  "st.contacted": { ar: "تم الاتصال", fr: "Contacté" },
  "st.qualified": { ar: "مؤهل", fr: "Qualifié" },
  "st.prospect": { ar: "محتمل", fr: "Prospect" },
  "st.sent": { ar: "مرسلة", fr: "Envoyée" },
  "st.pending": { ar: "في انتظار الرد", fr: "En attente" },
  "st.quiet": { ar: "هادئ", fr: "Peu actif" },
  "st.draft": { ar: "مسودة", fr: "Brouillon" },
  "st.expired": { ar: "منتهي", fr: "Expiré" },
  "st.overdue": { ar: "متأخرة", fr: "En retard" },
  "st.suspended": { ar: "معلّق", fr: "Suspendu" },
  "st.lost": { ar: "خاسرة", fr: "Perdue" },
  "st.rejected": { ar: "مرفوض", fr: "Rejeté" },
  "st.at_risk": { ar: "مهدد", fr: "À risque" },
  "st.cancelled": { ar: "ملغاة", fr: "Annulée" },
  "st.former": { ar: "سابق", fr: "Ancien client" },
  "st.none": { ar: "بدون اشتراك", fr: "Sans abonnement" },
  "st.high": { ar: "عاجل", fr: "Urgent" },
  "st.normal": { ar: "عادي", fr: "Normale" },
  "login.code": { ar: "رمز التحقق (6 أرقام)", fr: "Code de vérification (6 chiffres)" },
  "login.wrongCode": { ar: "الرمز غير صحيح", fr: "Code incorrect" },
  "login.forgot": { ar: "نسيت كلمة المرور؟", fr: "Mot de passe oublié ?" },
  "login.backToSignIn": { ar: "العودة إلى الدخول", fr: "Retour à la connexion" },
  "login.sendReset": { ar: "إرسال رابط إعادة التعيين", fr: "Envoyer le lien" },
  "login.resetSent": { ar: "إن كان الحساب موجودا، فقد أرسلنا رابطا إلى بريده.", fr: "Si ce compte existe, un lien lui a été envoyé." },
  "login.noAccount": { ar: "لا تملك حسابا؟ اطلب عرضا", fr: "Pas de compte ? Demandez une démo" },
  "pub.plans": { ar: "العروض", fr: "Offres" },
  "pub.footer": { ar: "الاجتهاد القضائي المغربي، بعد إزالة البيانات الشخصية.", fr: "La jurisprudence marocaine, données personnelles supprimées." },
  "pub.title": { ar: "الاجتهاد القضائي لمحكمة النقض، بالعربية والفرنسية", fr: "La jurisprudence de la Cour de cassation, en arabe et en français" },
  "pub.subtitle": { ar: "قرارات منشورة بعد إخفاء الأسماء، مع ملخص لكل قرار، وبحث وتنبيهات وملفات عمل لمكتبك.", fr: "Des décisions publiées sans les noms, un résumé pour chacune, la recherche, les alertes et des dossiers de travail pour votre cabinet." },
  "pub.onQuote": { ar: "على عرض سعر", fr: "Sur devis" },
  "pub.free": { ar: "مجانا", fr: "Gratuit" },
  "pub.perMonth": { ar: "/ شهر", fr: "/ mois" },
  "pub.perYear": { ar: "/ سنة", fr: "/ an" },
  "pub.exclVat": { ar: "دون احتساب الضريبة", fr: "HT" },
  "pub.seats": { ar: "مقاعد", fr: "accès" },
  "pub.downloadsDay": { ar: "تحميل في اليوم", fr: "téléchargements / jour" },
  "pub.bilingual": { ar: "بالعربية والفرنسية", fr: "Arabe et français" },
  "pub.startTrial": { ar: "ابدأ التجربة", fr: "Commencer l'essai" },
  "pub.askDemo": { ar: "اطلب عرضا", fr: "Demander une démo" },
  "pub.demoTitle": { ar: "اطلب عرضا تجريبيا", fr: "Demander une démonstration" },
  "pub.demoSubtitle": { ar: "نتصل بك لعرض المنصة وفتح تجربة مجانية لمدة 14 يوما.", fr: "Nous vous contactons pour présenter la plateforme et ouvrir un essai gratuit de 14 jours." },
  "pub.demoThanks": { ar: "شكرا، توصلنا بطلبك. سنتصل بك قريبا.", fr: "Merci, votre demande est bien reçue. Nous vous contactons rapidement." },
  "pub.name": { ar: "الاسم الكامل", fr: "Nom complet" },
  "pub.phone": { ar: "الهاتف", fr: "Téléphone" },
  "pub.company": { ar: "المكتب أو المؤسسة", fr: "Cabinet ou organisme" },
  "pub.message": { ar: "رسالتك (اختياري)", fr: "Votre message (facultatif)" },
  "pub.send": { ar: "إرسال", fr: "Envoyer" },
  "inv.title": { ar: "الانضمام إلى", fr: "Rejoindre" },
  "inv.accept": { ar: "إنشاء حسابي", fr: "Créer mon accès" },
  "inv.invalid": { ar: "هذه الدعوة لم تعد صالحة. اطلب دعوة جديدة.", fr: "Cette invitation n'est plus valable. Demandez-en une nouvelle." },
  "reset.title": { ar: "كلمة مرور جديدة", fr: "Nouveau mot de passe" },
  "reset.submit": { ar: "حفظ", fr: "Enregistrer" },
  "reset.done": { ar: "تم تغيير كلمة المرور.", fr: "Mot de passe modifié." },
  "acc.title": { ar: "حسابي", fr: "Mon compte" },
  "acc.subscription": { ar: "الاشتراك", fr: "Abonnement" },
  "acc.until": { ar: "إلى غاية", fr: "jusqu'au" },
  "acc.noSubscription": { ar: "لا يوجد اشتراك.", fr: "Aucun abonnement." },
  "acc.lapsed": { ar: "انتهى اشتراك مؤسستك، فلا يمكن الاطلاع على القرارات. لتجديده، تواصل معنا.", fr: "L'abonnement de votre organisation a pris fin : les décisions ne sont plus accessibles. Contactez-nous pour le renouveler." },
  "acc.profile": { ar: "الملف الشخصي", fr: "Profil" },
  "acc.emailLanguage": { ar: "لغة الرسائل", fr: "Langue des e-mails" },
  "acc.password": { ar: "كلمة المرور", fr: "Mot de passe" },
  "acc.currentPassword": { ar: "كلمة المرور الحالية", fr: "Mot de passe actuel" },
  "acc.newPassword": { ar: "كلمة المرور الجديدة", fr: "Nouveau mot de passe" },
  "acc.confirmPassword": { ar: "تأكيد كلمة المرور", fr: "Confirmer le mot de passe" },
  "acc.pwRule": { ar: "10 أحرف على الأقل.", fr: "10 caractères minimum." },
  "acc.pwOthers": { ar: "ستُغلق جلساتك على الأجهزة الأخرى.", fr: "Vos sessions sur les autres appareils seront fermées." },
  "acc.pwMismatch": { ar: "كلمتا المرور غير متطابقتين", fr: "Les mots de passe ne correspondent pas" },
  "acc.pwChanged": { ar: "تم تغيير كلمة المرور", fr: "Mot de passe modifié" },
  "mfa.title": { ar: "التحقق بخطوتين", fr: "Double authentification" },
  "mfa.explain": { ar: "رمز من تطبيق على هاتفك يُطلب عند كل دخول، إضافة إلى كلمة المرور.", fr: "Un code de votre téléphone est demandé à chaque connexion, en plus du mot de passe." },
  "mfa.isOn": { ar: "مفعّل: يُطلب رمز من هاتفك عند كل دخول.", fr: "Activée : un code de votre téléphone est demandé à chaque connexion." },
  "mfa.required": { ar: "مطلوب لحسابات الفريق.", fr: "Obligatoire pour les comptes de l'équipe." },
  "mfa.enable": { ar: "تفعيل", fr: "Activer" },
  "mfa.disable": { ar: "إلغاء التفعيل", fr: "Désactiver" },
  "mfa.confirm": { ar: "تأكيد", fr: "Confirmer" },
  "mfa.scan": { ar: "أضف هذا المفتاح في تطبيق المصادقة (Google Authenticator أو Microsoft Authenticator)، ثم أدخل الرمز الظاهر:", fr: "Ajoutez cette clé dans votre application d'authentification (Google Authenticator, Microsoft Authenticator), puis saisissez le code affiché :" },
  "mfa.openApp": { ar: "فتح في التطبيق", fr: "Ouvrir dans l'application" },
  "mfa.on": { ar: "تم التفعيل", fr: "Activée" },
  "mfa.off": { ar: "تم إلغاء التفعيل", fr: "Désactivée" },
  "mfa.onShort": { ar: "مفعّل", fr: "Activée" },
  "mfa.offShort": { ar: "غير مفعّل", fr: "Non activée" },
  "team.title": { ar: "فريق المكتب", fr: "L'équipe du cabinet" },
  "team.invite": { ar: "دعوة", fr: "Inviter" },
  "team.invited": { ar: "أُرسلت الدعوة", fr: "Invitation envoyée" },
  "team.noSeat": { ar: "لا مقاعد متاحة في اشتراككم", fr: "Plus d'accès disponible dans votre abonnement" },
  "team.pending": { ar: "دعوة مرسلة", fr: "Invitation envoyée" },
  "team.until": { ar: "صالحة إلى", fr: "valable jusqu'au" },
  "team.cancel": { ar: "إلغاء", fr: "Annuler" },
  "team.remove": { ar: "إزالة", fr: "Retirer" },
  "lib.title": { ar: "ملفاتي", fr: "Mes dossiers" },
  "lib.subtitle": { ar: "قرارات محفوظة مع ملاحظاتك", fr: "Décisions enregistrées, avec vos notes" },
  "lib.newName": { ar: "اسم ملف جديد", fr: "Nom du nouveau dossier" },
  "lib.create": { ar: "إنشاء", fr: "Créer" },
  "lib.shareFirm": { ar: "مشترك مع المكتب", fr: "Partagé avec le cabinet" },
  "lib.shared": { ar: "مشترك", fr: "partagé" },
  "lib.empty": { ar: "لا ملفات بعد. احفظ قرارا من صفحته.", fr: "Aucun dossier. Enregistrez une décision depuis sa page." },
  "lib.folderEmpty": { ar: "هذا الملف فارغ.", fr: "Ce dossier est vide." },
  "lib.delete": { ar: "حذف", fr: "Supprimer" },
  "lib.confirmDelete": { ar: "حذف هذا الملف وملاحظاته؟", fr: "Supprimer ce dossier et ses notes ?" },
  "lib.note": { ar: "ملاحظتك", fr: "Votre note" },
  "lib.remove": { ar: "إزالة من الملف", fr: "Retirer du dossier" },
  "lib.addedBy": { ar: "أضافه", fr: "Ajouté par" },
  "lib.save": { ar: "حفظ في ملف", fr: "Enregistrer" },
  "lib.inFolder": { ar: "محفوظ", fr: "Enregistré" },
  "lib.saved": { ar: "حُفظ في الملف", fr: "Enregistré dans le dossier" },
  "lib.chooseFolder": { ar: "اختر ملفا", fr: "Choisir un dossier" },
  "dl.quota": { ar: "بلغت حد التحميل اليومي", fr: "Limite de téléchargements du jour atteinte" },
  "dl.pace": { ar: "قراءة بوتيرة غير معتادة؛ أعد المحاولة لاحقا", fr: "Rythme de lecture inhabituel ; réessayez plus tard" },
  "alert.title": { ar: "تنبيهاتي", fr: "Mes alertes" },
  "alert.subtitle": { ar: "قرارات جديدة تصلك بالبريد", fr: "Les nouvelles décisions, par e-mail" },
  "alert.how": { ar: "أنشئ تنبيها من صفحة البحث: زر «إنشاء تنبيه» بعد البحث أو اختيار الموضوع.", fr: "Créez une alerte depuis la recherche : bouton « Créer une alerte » après une recherche ou un choix de sujet." },
  "alert.empty": { ar: "لا تنبيهات بعد.", fr: "Aucune alerte." },
  "alert.name": { ar: "التنبيه", fr: "Alerte" },
  "alert.criteria": { ar: "المعايير", fr: "Critères" },
  "alert.frequency": { ar: "الوتيرة", fr: "Fréquence" },
  "alert.daily": { ar: "يومي", fr: "Quotidienne" },
  "alert.weekly": { ar: "أسبوعي", fr: "Hebdomadaire" },
  "alert.lastSent": { ar: "آخر إرسال", fr: "Dernier envoi" },
  "alert.active": { ar: "مفعّل", fr: "Active" },
  "alert.create": { ar: "إنشاء تنبيه", fr: "Créer une alerte" },
  "alert.created": { ar: "أُنشئ التنبيه", fr: "Alerte créée" },
  "hist.title": { ar: "السجل", fr: "Historique" },
  "hist.subtitle": { ar: "ما قرأته وبحثت عنه", fr: "Ce que vous avez lu et cherché" },
  "hist.empty": { ar: "لا شيء بعد.", fr: "Rien pour l'instant." },
  "hist.searched": { ar: "بحث عن", fr: "Recherche" },
  "hist.read": { ar: "قرأ", fr: "Lu :" },
  "hist.downloaded": { ar: "حمّل", fr: "Téléchargé :" },
  "sup.subtitle": { ar: "اطرح سؤالا على فريقنا", fr: "Posez une question à notre équipe" },
  "sup.staffSubtitle": { ar: "طلبات العملاء", fr: "Les demandes des clients" },
  "sup.list": { ar: "الطلبات", fr: "Demandes" },
  "sup.all": { ar: "الكل", fr: "Toutes" },
  "sup.empty": { ar: "لا طلبات.", fr: "Aucune demande." },
  "sup.subject": { ar: "الموضوع", fr: "Objet" },
  "sup.updated": { ar: "آخر تحديث", fr: "Mise à jour" },
  "sup.new": { ar: "طلب جديد", fr: "Nouvelle demande" },
  "sup.describe": { ar: "صف طلبك", fr: "Décrivez votre demande" },
  "sup.priority": { ar: "الأولوية", fr: "Priorité" },
  "sup.close": { ar: "إغلاق الطلب", fr: "Clore la demande" },
  "sup.team": { ar: "فريق الدعم", fr: "L'équipe" },
  "sup.reply": { ar: "ردك", fr: "Votre réponse" },
  "crm.title": { ar: "إدارة العملاء", fr: "CRM" },
  "crm.subtitle": { ar: "المبيعات والتجديدات والعملاء", fr: "Ventes, renouvellements et clients" },
  "crm.dashboard": { ar: "لوحة القيادة", fr: "Tableau de bord" },
  "crm.leads": { ar: "الطلبات الواردة", fr: "Prospects" },
  "crm.orgs": { ar: "المؤسسات", fr: "Organisations" },
  "crm.tasks": { ar: "المهام", fr: "Tâches" },
  "crm.newLeads": { ar: "طلبات جديدة", fr: "Nouveaux prospects" },
  "crm.customers": { ar: "عملاء", fr: "Clients" },
  "crm.revenueMonth": { ar: "مداخيل الشهر", fr: "Encaissé ce mois" },
  "crm.outstanding": { ar: "في انتظار الأداء", fr: "Reste à encaisser" },
  "crm.myTasksDue": { ar: "مهامي المستحقة", fr: "Mes tâches dues" },
  "crm.pipeline": { ar: "مسار المبيعات", fr: "Pipeline" },
  "crm.stage": { ar: "المرحلة", fr: "Étape" },
  "crm.renewals": { ar: "تجديدات خلال 30 يوما", fr: "Renouvellements sous 30 jours" },
  "crm.noRenewals": { ar: "لا تجديدات قريبة.", fr: "Aucun renouvellement proche." },
  "crm.days": { ar: "يوما", fr: "jours" },
  "crm.atRisk": { ar: "عملاء مهددون", fr: "Clients à risque" },
  "crm.atRiskHint": { ar: "اشتراك ساري، ولم يفتح أحد منهم شيئا خلال 30 يوما.", fr: "Abonnement en cours, mais personne n'a rien ouvert depuis 30 jours." },
  "crm.noRisk": { ar: "لا أحد.", fr: "Aucun." },
  "crm.leadsSubtitle": { ar: "طلبات العرض والمحتملون", fr: "Demandes de démo et prospects" },
  "crm.newLead": { ar: "محتمل جديد", fr: "Nouveau prospect" },
  "crm.searchLeads": { ar: "بحث بالاسم أو المكتب أو البريد", fr: "Nom, cabinet ou e-mail" },
  "crm.noLeads": { ar: "لا طلبات.", fr: "Aucun prospect." },
  "crm.contact": { ar: "التواصل", fr: "Contact" },
  "crm.source": { ar: "المصدر", fr: "Source" },
  "crm.received": { ar: "التاريخ", fr: "Reçu le" },
  "crm.convert": { ar: "تحويل إلى عميل", fr: "Convertir" },
  "crm.converted": { ar: "أُنشئت المؤسسة والتجربة وأُرسلت الدعوة", fr: "Organisation, essai et invitation créés" },
  "crm.convertConfirm": { ar: "إنشاء المؤسسة، وفتح تجربة 14 يوما، وإرسال دعوة إلى هذا البريد؟", fr: "Créer l'organisation, ouvrir un essai de 14 jours et envoyer une invitation à cet e-mail ?" },
  "crm.open": { ar: "فتح", fr: "Ouvrir" },
  "crm.org": { ar: "المؤسسة", fr: "Organisation" },
  "crm.orgsSubtitle": { ar: "المكاتب والشركات والمؤسسات", fr: "Cabinets, entreprises et institutions" },
  "crm.newOrg": { ar: "مؤسسة جديدة", fr: "Nouvelle organisation" },
  "crm.searchOrgs": { ar: "بحث", fr: "Rechercher" },
  "crm.noOrgs": { ar: "لا مؤسسات.", fr: "Aucune organisation." },
  "crm.health": { ar: "النشاط", fr: "Activité" },
  "crm.actions30": { ar: "عملية في 30 يوما", fr: "actions en 30 jours" },
  "crm.manager": { ar: "المسؤول التجاري", fr: "Chargé de compte" },
  "crm.orgName": { ar: "الاسم", fr: "Nom" },
  "crm.kind": { ar: "النوع", fr: "Type" },
  "crm.address": { ar: "العنوان", fr: "Adresse" },
  "crm.notes": { ar: "ملاحظات", fr: "Notes" },
  "crm.tabOverview": { ar: "المعلومات", fr: "Informations" },
  "crm.tabPeople": { ar: "الأشخاص", fr: "Personnes" },
  "crm.tabActivity": { ar: "المتابعة", fr: "Suivi" },
  "crm.tabHistory": { ar: "السجل", fr: "Historique" },
  "crm.accounts": { ar: "الحسابات", fr: "Comptes d'accès" },
  "crm.contacts": { ar: "جهات الاتصال", fr: "Contacts" },
  "crm.noContacts": { ar: "لا جهات اتصال.", fr: "Aucun contact." },
  "crm.jobTitle": { ar: "الصفة", fr: "Fonction" },
  "crm.primary": { ar: "رئيسي", fr: "Principal" },
  "crm.staffOnlyAdmin": { ar: "تغيير أدوار الفريق من صلاحية المسؤول فقط.", fr: "Seul un administrateur modifie les rôles de l'équipe." },
  "crm.newSubscription": { ar: "اشتراك جديد أو تجديد", fr: "Nouvel abonnement ou renouvellement" },
  "crm.plan": { ar: "العرض", fr: "Offre" },
  "crm.renewHint": { ar: "التجديد يبدأ في اليوم الموالي لنهاية الاشتراك الجاري، فلا يضيع يوم.", fr: "Un renouvellement commence le lendemain de la fin de l'abonnement en cours : aucun jour perdu." },
  "crm.subscriptions": { ar: "الاشتراكات", fr: "Abonnements" },
  "crm.from": { ar: "من", fr: "Du" },
  "crm.opportunities": { ar: "فرص البيع", fr: "Opportunités" },
  "crm.oppTitle": { ar: "العنوان", fr: "Intitulé" },
  "crm.newOpp": { ar: "فرصة جديدة", fr: "Nouvelle opportunité" },
  "crm.noOpps": { ar: "لا فرص.", fr: "Aucune opportunité." },
  "crm.value": { ar: "القيمة السنوية", fr: "Valeur annuelle" },
  "crm.owner": { ar: "المسؤول", fr: "Responsable" },
  "crm.logActivity": { ar: "تسجيل تواصل", fr: "Noter un échange" },
  "crm.activityKind": { ar: "النوع", fr: "Type" },
  "crm.taskTitle": { ar: "مهمة جديدة", fr: "Nouvelle tâche" },
  "crm.tasksSubtitle": { ar: "ما يجب القيام به", fr: "Ce qu'il reste à faire" },
  "crm.onlyMine": { ar: "مهامي فقط", fr: "Seulement les miennes" },
  "crm.noTasks": { ar: "لا مهام مفتوحة.", fr: "Aucune tâche ouverte." },
  "bill.invoices": { ar: "الفواتير", fr: "Factures" },
  "bill.subtitle": { ar: "كل الفواتير والأداءات", fr: "Toutes les factures et les paiements" },
  "bill.none": { ar: "لا فواتير.", fr: "Aucune facture." },
  "bill.number": { ar: "الرقم", fr: "Numéro" },
  "bill.issued": { ar: "تاريخ الإصدار", fr: "Émise le" },
  "bill.due": { ar: "تاريخ الاستحقاق", fr: "Échéance" },
  "bill.total": { ar: "المبلغ مع الضريبة", fr: "Total TTC" },
  "bill.balance": { ar: "الباقي", fr: "Reste dû" },
  "bill.paid": { ar: "المؤدى", fr: "Réglé" },
  "bill.amountHt": { ar: "المبلغ دون ضريبة", fr: "Montant HT" },
  "bill.vat": { ar: "الضريبة على القيمة المضافة", fr: "TVA" },
  "bill.description": { ar: "البيان", fr: "Désignation" },
  "bill.invoice": { ar: "فاتورة", fr: "Facture" },
  "bill.billedTo": { ar: "الزبون", fr: "Facturé à" },
  "bill.payBy": { ar: "الأداء بالتحويل", fr: "Règlement par virement" },
  "bill.sellerMissing": { ar: "(اسم البائع في SELLER_NAME)", fr: "(nom du vendeur : SELLER_NAME)" },
  "bill.new": { ar: "فاتورة جديدة", fr: "Nouvelle facture" },
  "bill.created": { ar: "أُنشئت الفاتورة", fr: "Facture créée" },
  "bill.newHint": { ar: "الرقم تلقائي ومتسلسل، والضريبة 20٪، والاستحقاق بعد 30 يوما. تُرسل إلى بريد المؤسسة.", fr: "Numéro automatique et continu, TVA 20 %, échéance à 30 jours. Envoyée à l'e-mail de l'organisation." },
  "bill.recordPayment": { ar: "تسجيل أداء", fr: "Enregistrer un paiement" },
  "bill.paymentSaved": { ar: "سُجل الأداء", fr: "Paiement enregistré" },
  "bill.amount": { ar: "المبلغ", fr: "Montant" },
  "bill.method": { ar: "طريقة الأداء", fr: "Mode de paiement" },
  "bill.reference": { ar: "المرجع", fr: "Référence" },
  "bill.cancelConfirm": { ar: "إلغاء هذه الفاتورة؟ يبقى رقمها مستعملا.", fr: "Annuler cette facture ? Son numéro reste utilisé." },
  "bill.toCollect": { ar: "في انتظار الأداء", fr: "Reste à encaisser" },
  "bill.collected": { ar: "المؤدى", fr: "Encaissé" },
  "adm.tabStaff": { ar: "الفريق", fr: "Équipe" },
  "adm.tabPlans": { ar: "العروض والأسعار", fr: "Offres et prix" },
  "adm.tabMail": { ar: "الرسائل", fr: "E-mails" },
  "staff.new": { ar: "حساب فريق جديد", fr: "Nouveau compte d'équipe" },
  "staff.rolesHint": { ar: "محرر: القرارات وتصحيحها. مبيعات: إدارة العملاء والفواتير. مسؤول: كل شيء.", fr: "Éditeur : les décisions et leurs corrections. Commercial : CRM et factures. Administrateur : tout." },
  "plans.hint": { ar: "الأسعار هنا أمثلة يجب تحديدها قبل الإطلاق. التغيير يسري على الاشتراكات الجديدة.", fr: "Les prix sont des exemples à fixer avant le lancement. Un changement vaut pour les nouveaux abonnements." },
  "plans.name": { ar: "الاسم", fr: "Nom" },
  "plans.price": { ar: "السعر دون ضريبة", fr: "Prix HT" },
  "plans.period": { ar: "المدة", fr: "Période" },
  "plans.blurb": { ar: "الوصف", fr: "Description" },
  "plans.public": { ar: "يظهر في صفحة العروض", fr: "Visible sur la page Offres" },
  "plans.active": { ar: "متاح", fr: "Disponible" },
  "mail.hint": { ar: "كل الرسائل التي أرسلتها المنصة أو تنتظر الإرسال. بدون إعداد SMTP تبقى في الانتظار.", fr: "Tous les e-mails envoyés ou en attente. Sans réglage SMTP, ils restent en attente." },
  "mail.empty": { ar: "لا رسائل.", fr: "Aucun e-mail." },
  "mail.to": { ar: "إلى", fr: "À" },
  "mail.created": { ar: "التاريخ", fr: "Créé le" },

  // settings
  "settings.title": { ar: "الإعدادات", fr: "Paramètres" },
  "settings.subtitle": { ar: "الحساب والتفضيلات", fr: "Compte et préférences" },
  "settings.account": { ar: "الحساب", fr: "Compte" },
  "settings.role": { ar: "الدور", fr: "Rôle" },
  "settings.role.admin": { ar: "مسؤول", fr: "Administrateur" },
  "settings.role.client": { ar: "عميل", fr: "Client" },
  "settings.appearance": { ar: "المظهر واللغة", fr: "Apparence et langue" },

  // admin console
  "adm.title": { ar: "لوحة الإدارة", fr: "Console d'administration" },
  "adm.subtitle": { ar: "الاستيراد والمراجعة والنشر وحسابات العملاء", fr: "Import, révision, publication et comptes clients" },
  "adm.tabImport": { ar: "استيراد", fr: "Import" },
  "adm.tabQueue": { ar: "قائمة المراجعة", fr: "File de révision" },
  "adm.tabClients": { ar: "العملاء", fr: "Clients" },
  "adm.importTitle": { ar: "استيراد دفعة من المعالجة (.zip)", fr: "Importer un lot du pipeline (.zip)" },
  "adm.importHint": { ar: "يجب أن يحتوي الملف على records.json والملفات المجهولة. يعيد الاستيراد فحص كل ملف ويرفض ما يبدو أنه ما زال يحمل بيانات شخصية.", fr: "L'archive doit contenir records.json et les fichiers anonymisés. L'import revérifie chaque fichier et refuse tout ce qui semble encore personnel." },
  "adm.importing": { ar: "جارٍ الاستيراد…", fr: "Import en cours…" },
  "adm.choose": { ar: "اختيار ملف .zip", fr: "Choisir un .zip" },
  "adm.importDone": { ar: "تم الاستيراد", fr: "Import terminé" },
  "adm.importFailed": { ar: "فشل الاستيراد", fr: "Échec de l'import" },
  "adm.imported": { ar: "مستورد", fr: "Importés" },
  "adm.updated": { ar: "محدَّث", fr: "Mis à jour" },
  "adm.rejected": { ar: "مرفوض (بلا ملف)", fr: "Refusés (sans fichier)" },
  "adm.quarantined": { ar: "محجوز (بيانات شخصية)", fr: "En quarantaine (données personnelles)" },
  "adm.quarantinedList": { ar: "محجوز — ما زال يحمل أنماط بيانات شخصية:", fr: "En quarantaine — contient encore des données personnelles :" },
  "adm.colDecision": { ar: "القرار", fr: "Décision" },
  "adm.colAttention": { ar: "يحتاج إلى انتباه", fr: "À vérifier" },
  "adm.colAction": { ar: "إجراء", fr: "Action" },
  "adm.review": { ar: "مراجعة", fr: "Réviser" },
  "adm.publish": { ar: "نشر", fr: "Publier" },
  "adm.published": { ar: "نُشر", fr: "Publié" },
  "adm.queueClear": { ar: "لا شيء في انتظار المراجعة.", fr: "Rien à réviser." },
  "adm.failed": { ar: "تعذّر ذلك", fr: "Échec" },
  "adm.saved": { ar: "حُفظ", fr: "Enregistré" },
  "adm.save": { ar: "حفظ", fr: "Enregistrer" },
  "adm.loading": { ar: "جارٍ التحميل…", fr: "Chargement…" },
  "adm.openFile": { ar: "فتح الملف (.docx)", fr: "Ouvrir le fichier (.docx)" },
  "adm.verify": { ar: "للتحقق:", fr: "À vérifier :" },
  "adm.anonText": { ar: "النص المجهول — الأسماء مستبدلة بـ", fr: "Texte anonymisé — noms remplacés par" },
  "adm.noText": { ar: "لا معاينة للنص.", fr: "Pas d'aperçu du texte." },
  "adm.newClient": { ar: "عميل جديد", fr: "Nouveau client" },
  "adm.password": { ar: "كلمة المرور", fr: "mot de passe" },
  "adm.create": { ar: "إنشاء", fr: "Créer" },
  "adm.needEmail": { ar: "البريد وكلمة مرور من 6 أحرف على الأقل", fr: "E-mail et mot de passe de 6 caractères minimum" },
  "adm.clientCreated": { ar: "أُنشئ الحساب", fr: "Compte créé" },
  "adm.deleted": { ar: "حُذف", fr: "Supprimé" },
  "adm.colEmail": { ar: "البريد الإلكتروني", fr: "E-mail" },
  "adm.colStatus": { ar: "الحالة", fr: "Statut" },
  "adm.colLastLogin": { ar: "آخر دخول", fr: "Dernière connexion" },
  "adm.colActions": { ar: "إجراءات", fr: "Actions" },
  "adm.suspend": { ar: "تعليق", fr: "Suspendre" },
  "adm.activate": { ar: "تفعيل", fr: "Activer" },
  "adm.status.active": { ar: "نشط", fr: "Actif" },
  "adm.status.suspended": { ar: "معلّق", fr: "Suspendu" },
  "adm.noClients": { ar: "لا عملاء بعد.", fr: "Aucun client pour l'instant." },

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

const LEVELS: Record<string, Entry> = {
  "ابتدائي": { ar: "ابتدائي", fr: "Première instance" },
  "استئناف": { ar: "استئناف", fr: "Appel" },
  "نقض": { ar: "نقض", fr: "Cassation" },
};

/** What the court decided, as French rulings word it. */
const OUTCOMES: Record<string, Entry> = {
  "رفض الطلب": { ar: "رفض الطلب", fr: "Rejet du pourvoi" },
  "عدم القبول": { ar: "عدم القبول", fr: "Irrecevabilité" },
  "نقض وإحالة": { ar: "نقض وإحالة", fr: "Cassation et renvoi" },
  "نقض وإبطال": { ar: "نقض وإبطال", fr: "Cassation et annulation" },
  "نقض جزئي": { ar: "نقض جزئي", fr: "Cassation partielle" },
  "نقض بدون إحالة": { ar: "نقض بدون إحالة", fr: "Cassation sans renvoi" },
  "عدم الاختصاص": { ar: "عدم الاختصاص", fr: "Incompétence" },
  "تسجيل التنازل": { ar: "تسجيل التنازل", fr: "Désistement constaté" },
  "التشطيب على القضية": { ar: "التشطيب على القضية", fr: "Radiation de l'affaire" },
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
  level: (value: string) => string;
  outcome: (value: string) => string;
  /** a status word (active, overdue, trial...) as the language says it */
  status: (value: string) => string;
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
  // The address says which language: /ar/… or /fr/… (lib/lang-url.ts). The server
  // reads the same address, so it renders the right language from the first byte.
  const router = useRouter();
  const publicHref = useRouterState({ select: (s) => s.location.publicHref });
  const lang: Lang = langFromPath(publicHref) ?? getActiveLang();

  // An address with no language (an old link, a bookmark) gets one, so what is in the
  // bar can be shared as is.
  useEffect(() => {
    if (!langFromPath(publicHref)) router.history.replace(swapLang(publicHref, lang));
  }, [publicHref, lang, router]);

  const setLang = useCallback((l: Lang) => {
    setActiveLang(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* private browsing: the choice just does not persist */
    }
    router.history.push(swapLang(router.state.location.publicHref, l));
  }, [router]);

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
    level: (v) => LEVELS[v]?.[lang] ?? v,
    outcome: (v) => OUTCOMES[v]?.[lang] ?? v,
    status: (v) => (STRINGS as Record<string, Entry>)[`st.${v}`]?.[lang] ?? v,
    num: asRead,
  }), [lang, dir, setLang]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useI18n must be used inside <LanguageProvider>");
  return ctx;
}
