export type StatsPayload = {
  users: number;
  quizzes: number;
};

export type StatsState = {
  users: number | null;
  quizzes: number | null;
  isUnavailable: boolean;
};

export type FormStatus = "idle" | "loading" | "success" | "error";

export type LoginPayload = {
  requires_2fa: boolean;
};

export type AdminLoginCredentials = {
  login: string;
  password: string;
};

export type AdminLoginRequest = {
  email: string;
  password: string;
};

export type AdminLoginResult = {
  status: "idle" | "error";
  feedback: string | null;
  redirectTo: string | null;
};

export type ActiveWizard = "student" | "partner" | null;
