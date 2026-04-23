"use client";

import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import { apiRoutes } from "@/lib/api-routes";

import {
  ChoiceCards,
  ChoiceOption,
  HoneypotField,
  INPUT_CLASS,
  MultiChoiceCards,
  Spinner,
  StepIndicator,
  SubmitState,
  toggleInList,
  WizardProps,
} from "./contact-wizard-shared";

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
  company: string;
};

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
  company: "",
};

export function PartnerWizard({ onClose }: WizardProps) {
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
      await api.post(apiRoutes.public.contact, {
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
        company: form.company,
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
      <HoneypotField
        fieldId="partner-company"
        value={form.company}
        onChange={(value) => setForm((prev) => ({ ...prev, company: value }))}
      />
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
