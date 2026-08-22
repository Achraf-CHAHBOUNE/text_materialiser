export type Level = "ابتدائي" | "استئناف" | "نقض";
export type Review = "ok" | "check";

export type CaseRow = {
  id: string;
  chamber: string;
  trajectory: Level[];
  appealed: boolean;
  cassated: boolean;
  missing: Level[];
  review: Review;
};

export type StepNode = {
  level: Level;
  court: string;
  status: "done" | "missing";
  decisionNumber: string;
  fileNumber: string;
  date: string;
  outcome: string;
};

export type DocRow = {
  file: string;
  level: Level;
  chamber: string;
  pii: number;
  review: Review;
  caseId: string;
  jobId?: string;
};

export const LEVEL_ORDER: Level[] = ["ابتدائي", "استئناف", "نقض"];

export const LEVEL_COURT_LABEL: Record<Level, string> = {
  ابتدائي: "المحكمة الابتدائية",
  استئناف: "محكمة الاستئناف",
  نقض: "محكمة النقض",
};

export const cases: CaseRow[] = [
  {
    id: "C-1293/8222/2017",
    chamber: "الغرفة التجارية",
    trajectory: ["استئناف", "نقض"],
    appealed: true,
    cassated: true,
    missing: ["ابتدائي"],
    review: "check",
  },
  {
    id: "C-2249/4/1/2020",
    chamber: "الغرفة الإدارية",
    trajectory: ["نقض"],
    appealed: true,
    cassated: true,
    missing: ["ابتدائي", "استئناف"],
    review: "ok",
  },
  {
    id: "C-8888/1/2014",
    chamber: "الغرفة التجارية",
    trajectory: ["ابتدائي", "استئناف", "نقض"],
    appealed: true,
    cassated: true,
    missing: [],
    review: "ok",
  },
];

export const documents: DocRow[] = [
  {
    file: "3646_appel",
    level: "استئناف",
    chamber: "الغرفة الاستئنافية",
    pii: 1,
    review: "ok",
    caseId: "C-1293/8222/2017",
  },
  {
    file: "652_Cassation",
    level: "نقض",
    chamber: "غير محدد",
    pii: 0,
    review: "ok",
    caseId: "C-1293/8222/2017",
  },
  {
    file: "2021_1_4_0",
    level: "نقض",
    chamber: "الغرفة الإدارية",
    pii: 12,
    review: "ok",
    caseId: "C-2249/4/1/2020",
  },
  {
    file: "1174_premiere",
    level: "ابتدائي",
    chamber: "الغرفة التجارية",
    pii: 7,
    review: "ok",
    caseId: "C-8888/1/2014",
  },
  {
    file: "4102_appel",
    level: "استئناف",
    chamber: "الغرفة التجارية",
    pii: 4,
    review: "check",
    caseId: "C-8888/1/2014",
  },
  {
    file: "981_Cassation",
    level: "نقض",
    chamber: "الغرفة التجارية",
    pii: 3,
    review: "ok",
    caseId: "C-8888/1/2014",
  },
];

export const ANON_SAMPLE =
  "ينوب عنها الأساتذة XXXXXXX وXXXXXXX وXXXXXXX. المحامون بهيئة الدار البيضاء بواسطة الأستاذ XXXXXXX المقبول للترافع أمام محكمة النقض.";

export const ANON_SAMPLE_LONG = [
  "باسم جلالة الملك وطبقا للقانون، وبعد المداولة طبقا للقانون.",
  ANON_SAMPLE,
  "حيث إن الطاعنة تعيب على القرار المطعون فيه خرق المسطرة، ذلك أن المحكمة اعتمدت على تقرير الخبرة المنجز من طرف الخبير XXXXXXX دون استدعاء الطرف الطاعن.",
  "وحيث إن المطلوبة في النقض السيدة XXXXXXX أدلت بمذكرة جوابية بواسطة نائبها الأستاذ XXXXXXX التمست فيها رفض الطلب.",
];

export const caseSteps: Record<string, StepNode[]> = {
  "C-1293/8222/2017": [
    {
      level: "ابتدائي",
      court: "المحكمة التجارية بالرباط",
      status: "missing",
      decisionNumber: "حكم عدد 2618",
      fileNumber: "2015/8201/1174",
      date: "22/09/2016",
      outcome: "مشار إليه في القرار الاستئنافي",
    },
    {
      level: "استئناف",
      court: "محكمة الاستئناف التجارية بالدار البيضاء",
      status: "done",
      decisionNumber: "قرار عدد 3646",
      fileNumber: "1293/8222/2017",
      date: "19/06/2017",
      outcome: "تأييد مع تعديل",
    },
    {
      level: "نقض",
      court: "محكمة النقض",
      status: "done",
      decisionNumber: "قرار عدد 652/3",
      fileNumber: "2018/3/3/622",
      date: "12/12/2018",
      outcome: "رفض الطلب",
    },
  ],
  "C-2249/4/1/2020": [
    {
      level: "ابتدائي",
      court: "المحكمة الإدارية بالرباط",
      status: "missing",
      decisionNumber: "غير متوفر",
      fileNumber: "غير متوفر",
      date: "—",
      outcome: "غير متوفر",
    },
    {
      level: "استئناف",
      court: "محكمة الاستئناف الإدارية بالرباط",
      status: "missing",
      decisionNumber: "غير متوفر",
      fileNumber: "غير متوفر",
      date: "—",
      outcome: "غير متوفر",
    },
    {
      level: "نقض",
      court: "محكمة النقض",
      status: "done",
      decisionNumber: "قرار عدد 1042/1",
      fileNumber: "2021/1/4/2249",
      date: "05/05/2021",
      outcome: "نقض وإحالة",
    },
  ],
  "C-8888/1/2014": [
    {
      level: "ابتدائي",
      court: "المحكمة التجارية بالدار البيضاء",
      status: "done",
      decisionNumber: "حكم عدد 1174",
      fileNumber: "2014/1/8888",
      date: "14/03/2014",
      outcome: "الحكم بأداء المبلغ المطلوب",
    },
    {
      level: "استئناف",
      court: "محكمة الاستئناف التجارية بالدار البيضاء",
      status: "done",
      decisionNumber: "قرار عدد 4102",
      fileNumber: "2015/8222/4102",
      date: "28/10/2015",
      outcome: "تأييد الحكم المستأنف",
    },
    {
      level: "نقض",
      court: "محكمة النقض",
      status: "done",
      decisionNumber: "قرار عدد 981/2",
      fileNumber: "2017/3/3/981",
      date: "09/02/2017",
      outcome: "رفض الطلب",
    },
  ],
};

export type Job = {
  id: string;
  name: string;
  files: number;
  pii: number;
  status: "completed" | "processing" | "failed";
  date: string;
};

export const recentJobs: Job[] = [
  {
    id: "JOB-2041",
    name: "دفعة النقض التجارية 2018",
    files: 24,
    pii: 187,
    status: "completed",
    date: "12 Jul 2026",
  },
  {
    id: "JOB-2039",
    name: "أحكام إدارية — الرباط",
    files: 11,
    pii: 63,
    status: "completed",
    date: "09 Jul 2026",
  },
  {
    id: "JOB-2036",
    name: "استئناف الدار البيضاء Q2",
    files: 7,
    pii: 0,
    status: "failed",
    date: "04 Jul 2026",
  },
];

export const kpis = {
  processed: 1284,
  redacted: 9432,
  linked: 316,
  quota: 2000,
};
