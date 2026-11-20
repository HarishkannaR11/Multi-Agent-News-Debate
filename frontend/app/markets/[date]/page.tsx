import { Header } from "@/components/Header";
import { MarketView } from "@/components/markets/MarketView";

// One market day (address "/markets/<YYYY-MM-DD>").
export default async function MarketDayPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  return (
    <>
      <Header current="markets" />
      <main>
        <MarketView date={date} />
      </main>
    </>
  );
}
