import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GymBuddy · Make room for a good workout",
  description:
    "Find a quieter time at McComas Hall and War Memorial Hall. A Virginia Tech gym planning prototype.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
