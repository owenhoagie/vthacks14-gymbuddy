import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 90;

const endpoints: Record<string, string> = {
  health: "GET",
  occupancy: "GET",
  forecast: "GET",
  recommend: "POST",
};

function failure(status: number, code: string, message: string) {
  return Response.json({ error: { code, message, details: null } }, { status });
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const endpoint = path.join("/");
  if (!Object.hasOwn(endpoints, endpoint))
    return failure(404, "http_error", "Endpoint not found.");
  if (endpoints[endpoint] !== request.method)
    return failure(405, "http_error", "Method not allowed.");

  const configured = process.env.GYMBUDDY_API_URL;
  if (!configured)
    return failure(503, "api_not_configured", "The hosted API is not configured yet.");

  try {
    const origin = new URL(configured);
    if (!["https:", "http:"].includes(origin.protocol) || origin.username || origin.password)
      return failure(503, "api_not_configured", "The hosted API configuration is invalid.");
    const upstream = new URL(`${origin.pathname.replace(/\/$/, "")}/${endpoint}`, origin);
    upstream.search = request.nextUrl.search;
    const response = await fetch(upstream, {
      method: request.method,
      headers: { "Content-Type": "application/json" },
      body: request.method === "POST" ? await request.text() : undefined,
      signal: AbortSignal.timeout(85000),
      cache: "no-store",
      redirect: "error",
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return failure(502, "api_unavailable", "The gym API is temporarily unavailable. Try again.");
  }
}

export { proxy as GET, proxy as POST };
