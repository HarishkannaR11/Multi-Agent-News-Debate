// The type of the page metadata (title, description) that Next.js puts in the HTML <head>.
import type { Metadata } from "next";
// Three Google fonts, downloaded and served by Next.js itself (no request to Google from the visitor's browser).
import { Inter, JetBrains_Mono, Playfair_Display } from "next/font/google";
// The global stylesheet (Tailwind plus our colour variables and animations).
import "./globals.css";

// Headline font. "variable" is the CSS variable name that tailwind.config.ts refers to.
const playfair = Playfair_Display({
  // Only load the Latin letters to keep the download small.
  subsets: ["latin"],
  // Only the font weights actually used.
  weight: ["400", "600", "700"],
  variable: "--font-serif",
});

// Body-text font.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-sans",
});

// Monospace font for numbers and counters.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-mono",
});

// The browser tab title and the description search engines show.
export const metadata: Metadata = {
  title: "The Debate",
  description: "Five perspectives. One verdict.",
};

// The root layout: wraps every page on the site. "children" is whichever page is being shown.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The <html> tag: English language, with the three font variables attached as CSS classes.
    <html lang="en" className={`${playfair.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      {/* The page body: at least full-screen height, paper background, default font and text colour. */}
      <body className="min-h-screen bg-paper font-sans text-ink">
        {/* A centred column with a maximum width and side padding that grows on medium screens and up. */}
        <div className="mx-auto max-w-content px-6 md:px-12">{children}</div>
      </body>
    </html>
  );
}
