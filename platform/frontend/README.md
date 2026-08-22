# Anonymize Hub

uild a **polished, fully interactive frontend prototype** for a legal-tech SaaS called

**Anonymize** — a platform that removes personal information (PII) from **Arabic court

rulings** and links related case documents across court levels

(first instance → appeal → cassation / **ابتدائي → استئناف → نقض**).

Use realistic **Arabic mock data** (samples below). No real backend is required —

navigate between screens with in-app state, animate the processing, and populate tables

from the mock data. Make it feel production-grade.

## Screens (single app, left sidebar navigation)

1. **Login** — centered card: email + password, "Continue with Google", link to sign up. Brand logo/wordmark.

2. **Dashboard** — KPI tiles (Documents processed, PII redacted, Cases linked, Usage vs quota), a "New job" button, and a recent-jobs list with status chips.

3. **New Job (Upload)** — drag-and-drop area accepting `.pdf/.doc/.docx`; show uploaded files as removable chips with size; a "Start anonymization" primary button.

4. **Processing** — an **animated progress bar** (fills 0→100%), a live feed listing each document as it "completes" (file · court level · chamber · PII count · ✓/✗), then a "View results" button.

5. **Results** — two tabs:

   - **Documents**: sortable/filterable table (file, court level, chamber/الغرفة, PII count, review flag).

   - **Cases**: grouped table (case, chamber, trajectory, appealed/cassated pills, missing levels, review=check warning badge). Row click → Case Explorer.

6. **Case Explorer** — the signature component: a horizontal **court-level stepper**

   **المحكمة الابتدائية → محكمة الاستئناف → محكمة النقض**. Each node is a card showing

   court name, file number, decision number, date, and outcome. **Missing** levels

   (referenced but not uploaded) appear greyed/dashed. Below: the member documents, each

   opening a right-aligned (RTL) preview of the anonymized text with names shown as `XXXXXXX`.

7. **Billing & Usage** — current plan, a usage meter (documents this month vs quota),

   Free/Pro/Firm plan cards with an "Upgrade" CTA. (UI only.)

8. **Settings** — profile, workspace name + members list with roles, default replacement token, data-retention toggle.

## The hero component — court-level stepper (get this right)

A horizontal 3-step tracker. States per step: **done** (solid brand color, checkmark,

shows file/decision/date), **current/top** (highlighted), **missing** (dashed outline,

muted, label "غير متوفر"). Connect steps with an animated line. It must read

right-to-left for the Arabic labels but flow ابتدائي (right) → نقض (left) or use clear

directional arrows. Animate on mount.

## Design system

- **Feel:** trustworthy, legal-grade, precise. Lots of whitespace, rounded-xl cards, soft shadows.

- **Palette:** primary deep navy/indigo `#1E3A5F`, accent teal `#0E9F9A`, success green,

  warning amber (for `review=check`), danger red, slate-gray neutrals.

- **Typography:** Inter for the LTR app UI; an Arabic face like **"IBM Plex Sans Arabic"**

  or **"Cairo"** for Arabic content, right-aligned with `dir="rtl"` and comfortable line-height.

- **Dark + light** themes with a toggle (respect system default).

- **Components:** shadcn/ui-style — data tables with sticky headers + filter inputs, status

  chips/pills, progress bar, tabs, toasts, empty states, skeleton loaders, the stepper.

- **Motion:** subtle and tasteful (progress fill, stepper reveal, row hover).

- **Responsive** (mobile → desktop) and **accessible** (WCAG AA, keyboard, visible focus).

## Realistic mock data (use verbatim)

**Cases**

| case             | chamber (الغرفة)        | trajectory                                 | appealed | cassated | missing                         | review |

| ---------------- | ----------------------------- | ------------------------------------------ | -------- | -------- | ------------------------------- | ------ |

| C-1293/8222/2017 | الغرفة التجارية | استئناف → نقض                   | نعم   | نعم   | ابتدائي                  | check  |

| C-2249/4/1/2020  | الغرفة الإدارية | نقض                                     | نعم   | نعم   | ابتدائي، استئناف | ok     |

| C-8888/1/2014    | الغرفة التجارية | ابتدائي → استئناف → نقض | نعم   | نعم   | —                              | ok     |

**Case Explorer example (for C-1293/8222/2017)**

- **المحكمة التجارية بالرباط** — *missing* (غير متوفر) — referenced: حكم عدد 2618، ملف 2015/8201/1174، 22/09/2016

- **محكمة الاستئناف التجارية بالدار البيضاء** — done — قرار عدد **3646**، ملف **1293/8222/2017**، بتاريخ 19/06/2017، المنطوق: تأييد مع تعديل

- **محكمة النقض** — done — قرار عدد **652/3**، ملف **2018/3/3/622**، بتاريخ 12/12/2018، المنطوق: رفض الطلب

**Documents table**

| file          | level          | chamber                             | PII | review |

| ------------- | -------------- | ----------------------------------- | --- | ------ |

| 3646_appel    | استئناف | الغرفة الاستئنافية | 1   | ok     |

| 652_Cassation | نقض         | غير محدد                     | 0   | ok     |

| 2021_1_4_0    | نقض         | الغرفة الإدارية       | 12  | ok     |

**Anonymized text preview (RTL sample)**

> ينوب عنها الأساتذة XXXXXXX وXXXXXXX وXXXXXXX. المحامون بهيئة الدار البيضاء بواسطة الأستاذ XXXXXXX المقبول للترافع أمام محكمة النقض.

## Deliverable

A clean, modern, responsive, dark/light, RTL-correct interactive prototype covering the

screens above, with the court-level **stepper** as the standout element. Prioritize

visual quality and clarity of the case-trajectory concept.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://anonymize-arabic-cases.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/48a42f76-ecc5-4273-853c-f2b1401f025f).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
