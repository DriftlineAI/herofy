import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Unescape JSON-escaped characters in text for display.
 * Handles escaped quotes that may come from backend JSON serialization.
 */
export function unescapeText(text: string): string {
  if (!text) return text;
  return text
    .replace(/\\'/g, "'")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\');
}
