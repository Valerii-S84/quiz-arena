"use client";

import { FormEvent, ReactNode, useEffect, useState } from "react";

import { api } from "@/lib/api";

type WizardKind = "student" | "partner";
type SubmitState = "idle" | "loading" | "success" | "error";

type StudentFormState = {
  name: string;
  ageGroup: string;
  level: string;
  goals: string[];
  format: string;
  timeSlots: string[];
  frequency: string;
  budget: string;
  contact: string;
  message: string;
};

type PartnerFormState = {
  name: string;
  partnerType: string;
  country: string;
  studentCount: string;
  offerings: string[];
  contact: string;
  website: string;
  idea: string;
  startTimeline: string;
};

type WizardModalProps = {
  title: string;
  onClose: () => void;
  children: ReactNode;
};

type WizardProps = {
  onClose: () => void;
};

type ChoiceOption = {
  value: string;
  label: string;
  description?: string;
  icon?: string;
};

const STUDENT_AGE_OPTIONS: ChoiceOption[] = [
  { value: "unter_16", label: "Unter 16" },
  { value: "16_25", label: "16-25" },
  { value: "26_35", label: "26-35" },
  { value: "36_50", label: "36-50" },
  { value: "50_plus", label: "50+" },
];

const STUDENT_LEVEL_OPTIONS: ChoiceOption[] = [
  { value: "A1", label: "A1", description: "Nullniveau" },
  { value: "A2", label: "A2", description: "Anfänger" },
  { value: "B1", label: "B1", description: "Mittelstufe" },
  { value: "B2", label: "B2", description: "Gute Mittelstufe" },
  { value: "C1_C2", label: "C1/C2", description: "Fortgeschritten" },
  {
    value: "UNSICHER",
    label: "Ich weiß es nicht",
    description: "Bitte helft mir beim Einstufen",
  },
];

const STUDENT_GOAL_OPTIONS: ChoiceOption[] = [
  { value: "alltag", label: "Im Alltag sprechen" },
  { value: "pruefung", label: "Prüfung bestehen (Goethe/telc/TestDaF)" },
  { value: "karriere", label: "Arbeit / Karriere in Deutschland" },
  { value: "umzug", label: "Umzug / Auswanderung" },
  { value: "universitaet", label: "Studium an der Universität" },
  { value: "reisen", label: "Reisen" },
  { value: "hobby", label: "Interesse / Hobby" },
];

const STUDENT_FORMAT_OPTIONS: ChoiceOption[] = [
  { value: "individual", label: "Individuell mit Lehrkraft", icon: "👤" },
  { value: "group", label: "Mini-Gruppe (2-5 Personen)", icon: "👥" },
  { value: "self", label: "Selbstständig mit Bot/Material", icon: "📱" },
  { value: "undecided", label: "Noch nicht entschieden", icon: "🤷" },
];

const STUDENT_TIME_OPTIONS: ChoiceOption[] = [
  { value: "morning", label: "Morgen (bis 12:00)" },
  { value: "day", label: "Tag (12:00-17:00)" },
  { value: "evening", label: "Abend (nach 17:00)" },
  { value: "weekend", label: "Wochenende" },
];

const STUDENT_FREQUENCY_OPTIONS: ChoiceOption[] = [
  { value: "once", label: "1x pro Woche" },
  { value: "twice", label: "2x pro Woche" },
  { value: "three_plus", label: "3+ pro Woche" },
  { value: "daily", label: "Täglich" },
];

const STUDENT_BUDGET_OPTIONS: ChoiceOption[] = [
  { value: "bis_50", label: "Bis 50 EUR" },
  { value: "50_100", label: "50-100 EUR" },
  { value: "100_200", label: "100-200 EUR" },
  { value: "200_plus", label: "200+ EUR" },
  { value: "offen", label: "Noch unklar" },
];

const PARTNER_TYPE_OPTIONS: ChoiceOption[] = [
  { value: "tutor", label: "Privater Nachhilfelehrer", icon: "👩‍🏫" },
  { value: "school", label: "Sprachschule / Kurse", icon: "🏫" },
  { value: "platform", label: "Online-Plattform", icon: "📱" },
  { value: "creator", label: "Content Creator / Blogger", icon: "🎬" },
  { value: "other_org", label: "Andere Organisation", icon: "🏢" },
];

const PARTNER_STUDENT_COUNT_OPTIONS: ChoiceOption[] = [
  { value: "bis_10", label: "Bis 10" },
  { value: "10_50", label: "10-50" },
  { value: "50_200", label: "50-200" },
  { value: "200_plus", label: "200+" },
  { value: "start", label: "Ich starte gerade" },
];

const PARTNER_OFFERING_OPTIONS: ChoiceOption[] = [
  { value: "teaching", label: "Ich kann Unterricht für Quiz Arena Lernende geben" },
  { value: "ads", label: "Ich möchte Werbung / Integration platzieren" },
  { value: "content", label: "Ich habe Content (Video/Artikel/Materialien)" },
  { value: "product", label: "Ich möchte ein gemeinsames Produkt/Projekt" },
  { value: "other", label: "Etwas anderes" },
];

const PARTNER_TIMELINE_OPTIONS: ChoiceOption[] = [
  { value: "asap", label: "So schnell wie möglich" },
  { value: "month", label: "Innerhalb eines Monats" },
  { value: "explore", label: "Ich schaue mich erst um" },
];

const INITIAL_STUDENT_STATE: StudentFormState = {
  name: "",
  ageGroup: "",
  level: "",
  goals: [],
  format: "",
  timeSlots: [],
  frequency: "",
  budget: "",
  contact: "",
  message: "",
};

const INITIAL_PARTNER_STATE: PartnerFormState = {
  name: "",
  partnerType: "",
  country: "",
  studentCount: "",
  offerings: [],
  contact: "",
  website: "",
  idea: "",
  startTimeline: "",
};

const SELECT_BASE_CLASS =
  "rounded-xl border border-white/60 bg-white/70 p-3 text-left transition hover:border-sky-300 hover:bg-white";

const SELECT_ACTIVE_CLASS = "border-sky-500 bg-sky-50 shadow-[0_8px_24px_rgba(2,132,199,0.15)]";

const INPUT_CLASS =
  "w-full rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200";

function toggleInList(values: string[], value: string): string[] {
  if (values.includes(value)) {
    return values.filter((item) => item !== value);
  }
  return [...values, value];
}

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-[0.15em] text-slate-500">
        Schritt {current} von {total}
      </p>
      <div className="mt-2 flex gap-2">
        {Array.from({ length: total }, (_, index) => {
          const step = index + 1;
          const isActive = step <= current;
          return (
            <span
              key={step}
              className={`h-2 flex-1 rounded-full ${isActive ? "bg-sky-500" : "bg-slate-200"}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function ChoiceCards({
  options,
  value,
  onChange,
  columnsClass = "grid-cols-1 sm:grid-cols-2",
}: {
  options: ChoiceOption[];
  value: string;
  onChange: (value: string) => void;
  columnsClass?: string;
}) {
  return (
    <div className={`grid gap-2 ${columnsClass}`}>
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            className={`${SELECT_BASE_CLASS} ${isActive ? SELECT_ACTIVE_CLASS : ""}`}
            aria-pressed={isActive}
            onClick={() => onChange(option.value)}
          >
            <span className="text-sm font-medium text-slate-800">
              {option.icon ? `${option.icon} ` : ""}
              {option.label}
            </span>
            {option.description ? (
              <span className="mt-1 block text-xs text-slate-600">{option.description}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function MultiChoiceCards({
  options,
  values,
  onToggle,
  columnsClass = "grid-cols-1 sm:grid-cols-2",
}: {
  options: ChoiceOption[];
  values: string[];
  onToggle: (value: string) => void;
  columnsClass?: string;
}) {
  return (
    <div className={`grid gap-2 ${columnsClass}`}>
      {options.map((option) => {
        const isActive = values.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            className={`${SELECT_BASE_CLASS} ${isActive ? SELECT_ACTIVE_CLASS : ""}`}
            aria-pressed={isActive}
            onClick={() => onToggle(option.value)}
          >
            <span className="text-sm font-medium text-slate-800">
              {isActive ? "☑ " : "☐ "}
              {option.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
    />
  );
}

function WizardModal({ title, onClose, children }: WizardModalProps) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleEscape);

    return () => {
      window.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-white/35 px-4 py-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <section
        className="w-full max-w-[560px] rounded-2xl border border-white/50 bg-white/90 p-5 shadow-[0_24px_60px_rgba(15,23,42,0.18)] backdrop-blur-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-xl font-semibold text-slate-900">{title}</h3>
          <button
            type="button"
            className="rounded-full px-2 py-1 text-lg leading-none text-slate-600 transition hover:bg-slate-100"
            onClick={onClose}
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>
        <div className="mt-4 max-h-[78vh] overflow-y-auto pr-1">{children}</div>
      </section>
    </div>
  );
}

function StudentWizard({ onClose }: WizardProps) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<StudentFormState>(INITIAL_STUDENT_STATE);
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submittedName, setSubmittedName] = useState("");

  function validateCurrentStep(currentStep: number): string | null {
    if (currentStep === 1) {
      if (!form.name.trim()) {
        return "Bitte gib deinen Namen ein.";
      }
      if (!form.ageGroup) {
        return "Bitte wähle eine Altersgruppe.";
      }
      if (!form.level) {
        return "Bitte wähle dein aktuelles Deutschniveau.";
      }
      if (!form.goals.length) {
        return "Bitte wähle mindestens ein Lernziel.";
      }
      return null;
    }

    if (currentStep === 2) {
      if (!form.format) {
        return "Bitte wähle einen Lernformat-Wunsch.";
      }
      if (!form.timeSlots.length) {
        return "Bitte wähle mindestens ein Zeitfenster.";
      }
      if (!form.frequency) {
        return "Bitte wähle, wie oft du lernen möchtest.";
      }
      return null;
    }

    if (!form.contact.trim()) {
      return "Bitte gib Telegram oder Email an.";
    }

    return null;
  }

  function handleNext() {
    const validationError = validateCurrentStep(step);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }
    setErrorMessage(null);
    setStep((current) => Math.min(current + 1, 3));
  }

  function handleBack() {
    setErrorMessage(null);
    setStep((current) => Math.max(current - 1, 1));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const validationError = validateCurrentStep(3);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setSubmitState("loading");
    setErrorMessage(null);

    try {
      await api.post("/api/contact", {
        type: "student",
        name: form.name.trim(),
        ageGroup: form.ageGroup,
        level: form.level,
        goals: form.goals,
        format: form.format,
        timeSlots: form.timeSlots,
        frequency: form.frequency,
        budget: form.budget,
        contact: form.contact.trim(),
        message: form.message.trim(),
      });
      setSubmittedName(form.name.trim());
      setSubmitState("success");
    } catch {
      setSubmitState("error");
      setErrorMessage("Etwas ist schiefgelaufen. Bitte versuche es erneut.");
    }
  }

  if (submitState === "success") {
    return (
      <div className="space-y-4 py-6 text-center">
        <p className="text-5xl">✅</p>
        <h4 className="text-2xl font-semibold text-slate-900">Danke, {submittedName}!</h4>
        <p className="text-sm text-slate-600">
          Wir haben deine Anfrage erhalten und suchen die beste Lernoption für dich. Wir melden uns
          innerhalb von 24 Stunden.
        </p>
        <button
          type="button"
          className="rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
          onClick={onClose}
        >
          Zurück zur Startseite
        </button>
      </div>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <StepIndicator current={step} total={3} />

      {step === 1 ? (
        <div className="space-y-4">
          <label className="block text-sm font-medium text-slate-700">
            Wie heißt du?
            <input
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              placeholder="Dein Name"
              autoComplete="name"
            />
          </label>

          <div>
            <p className="text-sm font-medium text-slate-700">Wie alt bist du?</p>
            <div className="mt-2">
              <ChoiceCards
                options={STUDENT_AGE_OPTIONS}
                value={form.ageGroup}
                onChange={(value) => setForm((prev) => ({ ...prev, ageGroup: value }))}
              />
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-700">Wie ist dein aktuelles Deutschniveau?</p>
            <div className="mt-2">
              <ChoiceCards
                options={STUDENT_LEVEL_OPTIONS}
                value={form.level}
                onChange={(value) => setForm((prev) => ({ ...prev, level: value }))}
                columnsClass="grid-cols-1"
              />
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-700">Was ist dein Hauptziel?</p>
            <div className="mt-2">
              <MultiChoiceCards
                options={STUDENT_GOAL_OPTIONS}
                values={form.goals}
                onToggle={(value) =>
                  setForm((prev) => ({ ...prev, goals: toggleInList(prev.goals, value) }))
                }
                columnsClass="grid-cols-1"
              />
            </div>
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-slate-700">Wie möchtest du lernen?</p>
            <div className="mt-2">
              <ChoiceCards
                options={STUDENT_FORMAT_OPTIONS}
                value={form.format}
                onChange={(value) => setForm((prev) => ({ ...prev, format: value }))}
              />
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-700">Wann passt es dir?</p>
            <div className="mt-2">
              <MultiChoiceCards
                options={STUDENT_TIME_OPTIONS}
                values={form.timeSlots}
                onToggle={(value) =>
                  setForm((prev) => ({ ...prev, timeSlots: toggleInList(prev.timeSlots, value) }))
                }
              />
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-700">Wie oft pro Woche?</p>
            <div className="mt-2">
              <ChoiceCards
                options={STUDENT_FREQUENCY_OPTIONS}
                value={form.frequency}
                onChange={(value) => setForm((prev) => ({ ...prev, frequency: value }))}
              />
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-700">Budget pro Monat (optional)</p>
            <div className="mt-2">
              <ChoiceCards
                options={STUDENT_BUDGET_OPTIONS}
                value={form.budget}
                onChange={(value) => setForm((prev) => ({ ...prev, budget: value }))}
              />
            </div>
          </div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="space-y-4">
          <label className="block text-sm font-medium text-slate-700">
            Telegram oder Email
            <input
              value={form.contact}
              onChange={(event) => setForm((prev) => ({ ...prev, contact: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              placeholder="@username oder email@beispiel.de"
              autoComplete="email"
            />
            <span className="mt-1 block text-xs text-slate-500">Wir schreiben dir innerhalb von 24 Stunden.</span>
          </label>

          <label className="block text-sm font-medium text-slate-700">
            Möchtest du etwas ergänzen? (optional)
            <textarea
              value={form.message}
              onChange={(event) => setForm((prev) => ({ ...prev, message: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              rows={3}
              placeholder="Zum Beispiel: Ich habe schon gelernt, suche eine bestimmte Lehrkraft oder brauche Prüfungsvorbereitung."
            />
          </label>
        </div>
      ) : null}

      {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}

      <div className="flex items-center justify-between gap-3 pt-1">
        <button
          type="button"
          onClick={handleBack}
          className={`rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 ${step === 1 ? "invisible" : ""}`}
        >
          ← Zurück
        </button>

        {step < 3 ? (
          <button
            type="button"
            onClick={handleNext}
            className="rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            Weiter →
          </button>
        ) : (
          <button
            type="submit"
            disabled={submitState === "loading"}
            className="inline-flex items-center gap-2 rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {submitState === "loading" ? (
              <>
                <Spinner /> Wird gesendet...
              </>
            ) : (
              "Anfrage senden →"
            )}
          </button>
        )}
      </div>
    </form>
  );
}

function PartnerWizard({ onClose }: WizardProps) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<PartnerFormState>(INITIAL_PARTNER_STATE);
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function validateCurrentStep(currentStep: number): string | null {
    if (currentStep === 1) {
      if (!form.name.trim()) {
        return "Bitte gib deinen Namen oder den Organisationsnamen ein.";
      }
      if (!form.partnerType) {
        return "Bitte wähle aus, wer ihr seid.";
      }
      if (!form.country.trim()) {
        return "Bitte gib Land/Stadt an.";
      }
      if (!form.studentCount) {
        return "Bitte wähle die aktuelle Zahl eurer Lernenden.";
      }
      if (!form.offerings.length) {
        return "Bitte wähle mindestens ein Kooperationsangebot.";
      }
      return null;
    }

    if (!form.contact.trim()) {
      return "Bitte gib Telegram oder Email an.";
    }
    if (!form.idea.trim()) {
      return "Bitte beschreibe eure Idee.";
    }
    if (!form.startTimeline) {
      return "Bitte gib an, wann ihr starten möchtet.";
    }

    return null;
  }

  function handleNext() {
    const validationError = validateCurrentStep(step);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }
    setErrorMessage(null);
    setStep((current) => Math.min(current + 1, 2));
  }

  function handleBack() {
    setErrorMessage(null);
    setStep((current) => Math.max(current - 1, 1));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const validationError = validateCurrentStep(2);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setSubmitState("loading");
    setErrorMessage(null);

    try {
      await api.post("/api/contact", {
        type: "partner",
        name: form.name.trim(),
        partnerType: form.partnerType,
        country: form.country.trim(),
        studentCount: form.studentCount,
        offerings: form.offerings,
        contact: form.contact.trim(),
        website: form.website.trim(),
        idea: form.idea.trim(),
        startTimeline: form.startTimeline,
      });
      setSubmitState("success");
    } catch {
      setSubmitState("error");
      setErrorMessage("Etwas ist schiefgelaufen. Bitte versuche es erneut.");
    }
  }

  if (submitState === "success") {
    return (
      <div className="space-y-4 py-6 text-center">
        <p className="text-5xl">✅</p>
        <h4 className="text-2xl font-semibold text-slate-900">Danke für euren Vorschlag!</h4>
        <p className="text-sm text-slate-600">
          Wir prüfen eure Anfrage und melden uns innerhalb von 2-3 Werktagen.
        </p>
        <button
          type="button"
          className="rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
          onClick={onClose}
        >
          Zurück zur Startseite
        </button>
      </div>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <StepIndicator current={step} total={2} />

      {step === 1 ? (
        <div className="space-y-4">
          <label className="block text-sm font-medium text-slate-700">
            Name oder Organisation
            <input
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              placeholder="Name / Organisation"
              autoComplete="organization"
            />
          </label>

          <div>
            <p className="text-sm font-medium text-slate-700">Wer seid ihr?</p>
            <div className="mt-2">
              <ChoiceCards
                options={PARTNER_TYPE_OPTIONS}
                value={form.partnerType}
                onChange={(value) => setForm((prev) => ({ ...prev, partnerType: value }))}
              />
            </div>
          </div>

          <label className="block text-sm font-medium text-slate-700">
            In welchem Land arbeitet ihr?
            <input
              value={form.country}
              onChange={(event) => setForm((prev) => ({ ...prev, country: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              placeholder="Land / Stadt"
            />
          </label>

          <div>
            <p className="text-sm font-medium text-slate-700">Wie viele Lernende habt ihr aktuell?</p>
            <div className="mt-2">
              <ChoiceCards
                options={PARTNER_STUDENT_COUNT_OPTIONS}
                value={form.studentCount}
                onChange={(value) => setForm((prev) => ({ ...prev, studentCount: value }))}
              />
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-700">Was bietet ihr für eine Kooperation an?</p>
            <div className="mt-2">
              <MultiChoiceCards
                options={PARTNER_OFFERING_OPTIONS}
                values={form.offerings}
                onToggle={(value) =>
                  setForm((prev) => ({ ...prev, offerings: toggleInList(prev.offerings, value) }))
                }
                columnsClass="grid-cols-1"
              />
            </div>
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4">
          <label className="block text-sm font-medium text-slate-700">
            Telegram oder Email
            <input
              value={form.contact}
              onChange={(event) => setForm((prev) => ({ ...prev, contact: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              placeholder="@username oder email@beispiel.de"
              autoComplete="email"
            />
          </label>

          <label className="block text-sm font-medium text-slate-700">
            Website oder Social Media (optional)
            <input
              value={form.website}
              onChange={(event) => setForm((prev) => ({ ...prev, website: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              placeholder="Damit wir eure Arbeit kennenlernen"
            />
          </label>

          <label className="block text-sm font-medium text-slate-700">
            Erzählt uns von eurer Idee
            <textarea
              value={form.idea}
              onChange={(event) => setForm((prev) => ({ ...prev, idea: event.target.value }))}
              className={`${INPUT_CLASS} mt-2`}
              rows={4}
              placeholder="Was bietet ihr an und was erwartet ihr von der Kooperation?"
            />
          </label>

          <div>
            <p className="text-sm font-medium text-slate-700">Wie schnell möchtet ihr starten?</p>
            <div className="mt-2">
              <ChoiceCards
                options={PARTNER_TIMELINE_OPTIONS}
                value={form.startTimeline}
                onChange={(value) => setForm((prev) => ({ ...prev, startTimeline: value }))}
                columnsClass="grid-cols-1"
              />
            </div>
          </div>
        </div>
      ) : null}

      {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}

      <div className="flex items-center justify-between gap-3 pt-1">
        <button
          type="button"
          onClick={handleBack}
          className={`rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 ${step === 1 ? "invisible" : ""}`}
        >
          ← Zurück
        </button>

        {step < 2 ? (
          <button
            type="button"
            onClick={handleNext}
            className="rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            Weiter →
          </button>
        ) : (
          <button
            type="submit"
            disabled={submitState === "loading"}
            className="inline-flex items-center gap-2 rounded-full bg-slate-800 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {submitState === "loading" ? (
              <>
                <Spinner /> Wird gesendet...
              </>
            ) : (
              "Vorschlag senden →"
            )}
          </button>
        )}
      </div>
    </form>
  );
}

export function ContactWizardModal({
  kind,
  isOpen,
  onClose,
}: {
  kind: WizardKind;
  isOpen: boolean;
  onClose: () => void;
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <WizardModal
      title={kind === "student" ? "Zum Unterricht anmelden" : "Kooperation / Partnerschaft"}
      onClose={onClose}
    >
      {kind === "student" ? <StudentWizard onClose={onClose} /> : <PartnerWizard onClose={onClose} />}
    </WizardModal>
  );
}
