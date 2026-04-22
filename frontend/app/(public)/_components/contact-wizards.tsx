"use client";

import { PartnerWizard } from "./contact-wizard-partner";
import { StudentWizard } from "./contact-wizard-student";
import { WizardKind, WizardModal } from "./contact-wizard-shared";

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
