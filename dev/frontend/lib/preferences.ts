export const PREFERENCE_GROUPS = [
  {
    id: "season",
    label: "Season",
    options: [
      { emoji: "🌸", id: "spring", label: "Spring" },
      { emoji: "☀️", id: "summer", label: "Summer" },
      { emoji: "🍂", id: "autumn", label: "Autumn" },
      { emoji: "❄️", id: "winter", label: "Winter" },
    ],
  },
  {
    id: "food-drink",
    label: "Food & drink",
    options: [
      { emoji: "🥬", id: "vegetarian", label: "Vegetarian" },
      { emoji: "🍽️", id: "local-cuisine", label: "Local cuisine" },
      { emoji: "☕", id: "cafes", label: "Cafés" },
      { emoji: "🍷", id: "wine", label: "Wine" },
      { emoji: "🍸", id: "bars-nightlife", label: "Bars & nightlife" },
    ],
  },
] as const;

const PREFERENCE_IDS = new Set<string>(
  PREFERENCE_GROUPS.flatMap((group) =>
    group.options.map((option) => option.id),
  ),
);

export function parsePreferences(value: unknown) {
  const values = Array.isArray(value) ? value : [value];

  return Array.from(
    new Set(
      values.filter(
        (item): item is string =>
          typeof item === "string" && PREFERENCE_IDS.has(item),
      ),
    ),
  );
}
