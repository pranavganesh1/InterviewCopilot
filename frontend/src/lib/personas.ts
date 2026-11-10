export type PersonaId =
  | "balanced"
  | "architect"
  | "hiring_manager"
  | "academic";

export interface PersonaOption {
  id: PersonaId;
  name: string;
  description: string;
  tags: string[];
  initials: string;
  accent: string;
}

export const PERSONA_OPTIONS: PersonaOption[] = [
  {
    id: "balanced",
    name: "Balanced",
    description: "Even coverage of concepts, practice, and judgment.",
    tags: ["Coverage", "Clarity", "Progression"],
    initials: "B",
    accent: "#6d28d9",
  },
  {
    id: "architect",
    name: "The Strict Architect",
    description: "Presses on structure, reliability, and trade-offs.",
    tags: ["Trade-offs", "Reliability", "Failure modes"],
    initials: "SA",
    accent: "#5b21b6",
  },
  {
    id: "hiring_manager",
    name: "The Hiring Manager",
    description: "Focuses on ownership, delivery, and impact.",
    tags: ["Ownership", "Delivery", "Impact"],
    initials: "HM",
    accent: "#7c3aed",
  },
  {
    id: "academic",
    name: "The Academic Deep-Diver",
    description: "Digs into fundamentals, complexity, and why methods work.",
    tags: ["Fundamentals", "Complexity", "Why it works"],
    initials: "AD",
    accent: "#8b5cf6",
  },
];

const STORAGE_KEY = "ic_persona_id";

export function readStoredPersonaId(): PersonaId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (PERSONA_OPTIONS.some((p) => p.id === raw)) return raw as PersonaId;
  } catch {
    /* ignore */
  }
  return "balanced";
}

export function storePersonaId(id: PersonaId): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

export function personaById(id: string | null | undefined): PersonaOption {
  return PERSONA_OPTIONS.find((p) => p.id === id) ?? PERSONA_OPTIONS[0];
}
