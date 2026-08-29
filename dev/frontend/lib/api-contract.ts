export type ApiError = {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    request_id: string;
  };
};

export type ItineraryAccepted = {
  id: string;
  status: "pending" | "done" | "fail";
  status_url: string;
};

export type PreferenceEntry = {
  id: string;
  name: string;
  category: "food" | "drinks_party" | "culture" | "nature";
  description: string;
  image_link: string;
  decision: "like" | "dislike" | null;
};

export type PreferencePage = {
  id: string;
  position: number;
  layout: "single" | "pair";
  source: "initial" | "adaptive";
  entries: PreferenceEntry[];
};

export type PlaceLink = {
  kind: "map" | "official" | "source";
  label: string;
  url: string;
};

export type ItineraryResource = {
  id: string;
  city: string;
  tags: string[];
  status: "pending" | "done" | "fail";
  stage:
    | "learning_preferences"
    | "queued"
    | "researching"
    | "planning"
    | "illustrating"
    | null;
  result: {
    destination: string;
    planned_date: string;
    destination_timezone: string;
    title: string;
    summary: string;
    journal_image: {
      id: string;
      url: string;
      content_type: string;
      width: number;
      height: number;
      alt_text: string;
    };
    places: Array<{
      id: string;
      position: number;
      start_time: string;
      end_time: string;
      name: string;
      category: string;
      description: string;
      reason_to_visit: string;
      location: {
        address: string | null;
        latitude: number | null;
        longitude: number | null;
      } | null;
      links: PlaceLink[];
    }>;
  } | null;
  error: ApiError["error"] | null;
};
