import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { MarketView } from "@/components/markets/MarketView";

export const metadata: Metadata = { title: "Markets · The Debate" };

// The latest market day (address "/markets").
export default function MarketsPage() {
  return (
    <>
      <Header current="markets" />
      <main>
        <MarketView date="latest" />
      </main>
    </>
  );
}
