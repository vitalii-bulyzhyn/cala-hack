export const MAX_DESTINATION_LENGTH = 80;

export function parseDestination(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }

  const destination = value.trim();

  if (
    destination.length < 2 ||
    destination.length > MAX_DESTINATION_LENGTH
  ) {
    return null;
  }

  return destination;
}
