import type { BadgeTone } from "../components/ui/Badge";

export const COVERAGE_TONE: Record<string, BadgeTone> = {
  excellent: "success",
  good: "success",
  partial: "warn",
  none: "danger",
};

export const LEVEL_TONE: Record<string, BadgeTone> = {
  strong: "success",
  solid: "success",
  developing: "warn",
  weak: "danger",
};
