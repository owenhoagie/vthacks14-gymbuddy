import type { Metadata } from "next";
import { Montserrat } from "next/font/google";
import "./globals.css";

const montserrat = Montserrat({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-montserrat",
});

export const metadata: Metadata = {
  title: "GymBuddy · Make room for a good workout",
  description:
    "Find a quieter time at McComas Hall and War Memorial Hall. A Virginia Tech gym planning prototype.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={montserrat.variable}
      data-theme="light"
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try { document.documentElement.dataset.theme = localStorage.getItem("gymbuddy-theme") === "dark" ? "dark" : "light"; } catch {}`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
