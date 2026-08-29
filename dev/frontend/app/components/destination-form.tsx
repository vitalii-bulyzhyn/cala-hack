"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import styles from "@/app/journey-flow.module.css";
import { parseDestination, SUPPORTED_DESTINATIONS } from "@/lib/destination";
import { PREFERENCE_GROUPS } from "@/lib/preferences";
import { createItinerary } from "@/lib/api-client";

export function DestinationForm() {
  const router = useRouter();
  const inputRef = useRef<HTMLSelectElement>(null);
  const idempotencyKeyRef = useRef<string | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedPreferences, setSelectedPreferences] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function togglePreference(preference: string) {
    idempotencyKeyRef.current = null;
    setSelectedPreferences((currentPreferences) =>
      currentPreferences.includes(preference)
        ? currentPreferences.filter((item) => item !== preference)
        : [...currentPreferences, preference],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const destination = parseDestination(query);

    if (!destination) {
      setError("Enter a destination to continue.");
      inputRef.current?.focus();
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      idempotencyKeyRef.current ??= crypto.randomUUID();
      const itinerary = await createItinerary(
        destination,
        selectedPreferences,
        idempotencyKeyRef.current,
      );
      router.push(`/preferences?id=${encodeURIComponent(itinerary.id)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start your journal.");
      setIsSubmitting(false);
    }
  }

  return (
    <form className={styles.startForm} noValidate onSubmit={handleSubmit}>
      <div className={styles.locationField}>
        <label className={styles.fieldLabel} htmlFor="destination">
          Location
        </label>
        <select
          aria-describedby={error ? "destination-error" : undefined}
          aria-invalid={error ? true : undefined}
          className={styles.queryInput}
          id="destination"
          name="destination"
          onChange={(event) => {
            setQuery(event.target.value);
            idempotencyKeyRef.current = null;
            if (error) {
              setError(null);
            }
          }}
          ref={inputRef}
          required
          value={query}
        >
          <option value="">Choose a city</option>
          {SUPPORTED_DESTINATIONS.map((destination) => (
            <option key={destination} value={destination}>
              {destination}
            </option>
          ))}
        </select>
        {error ? (
          <p className={styles.formError} id="destination-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <div className={styles.preferenceGroups}>
        {PREFERENCE_GROUPS.map((group) => (
          <fieldset className={styles.preferenceFieldset} key={group.id}>
            <legend className={styles.preferenceLegend}>{group.label}</legend>
            <div className={styles.preferenceOptions}>
              {group.options.map((option) => {
                const isSelected = selectedPreferences.includes(option.id);

                return (
                  <button
                    aria-pressed={isSelected}
                    className={styles.preferenceChip}
                    key={option.id}
                    onClick={() => togglePreference(option.id)}
                    type="button"
                  >
                    <span aria-hidden="true" className={styles.preferenceEmoji}>
                      {option.emoji}
                    </span>
                    {option.label}
                  </button>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>

      <button className={styles.startButton} disabled={isSubmitting} type="submit">
        {isSubmitting ? "Starting…" : "Start"}
      </button>
    </form>
  );
}
