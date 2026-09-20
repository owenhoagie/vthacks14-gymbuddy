import { NextRequest } from "next/server";
import { getDiningMenu } from "@/lib/dining-snapshot";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const hall = request.nextUrl.searchParams.get("hall") || "15";
  const menu = getDiningMenu(hall);
  if (!menu) {
    return Response.json(
      { error: { code: "unknown_dining_hall", message: "Choose a supported dining hall." } },
      { status: 400 },
    );
  }
  // Serve the committed snapshot only. Browsing and hall changes never query VT.
  return Response.json(menu);
}
