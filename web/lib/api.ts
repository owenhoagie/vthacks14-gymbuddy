import type { components } from "./api-types";
export type OccupancyResponse = components["schemas"]["OccupancyResponse"];
export type ForecastResponse = components["schemas"]["ForecastResponse"];
export type RecommendationResponse =
  components["schemas"]["RecommendationResponse"];
export type RecommendationRequest =
  components["schemas"]["RecommendationRequest"];
export type Candidate = components["schemas"]["Candidate"];
export type FacilityId = components["schemas"]["FacilityId"];
export type HealthResponse = components["schemas"]["HealthResponse"];

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    signal: options.signal ?? AbortSignal.timeout(20000),
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.error?.message ||
        `The request failed (${response.status}). Please try again.`,
    );
  }
  return response.json() as Promise<T>;
}
