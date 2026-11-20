// Runs in the browser: loads the recent days for the chips.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchMarketDays, regimeLabel, signedPct, type MarketSummary } from "@/lib/markets";
import { formatDay } from "@/lib/debate";

// Recent market days as links, so any earlier day can be opened (the address of each day never changes).
export function DayPicker({ current }: { current: string }) {
  const [days, setDays] = useState<MarketSummary[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchMarketDays(14)
      .then((r) => !cancelled && setDays(r.items))
      .catch(() => !cancelled && setDays([]));
    return () => {
      cancelled = true;
    };
  }, []);
  if (!days || days.length === 0) return null;
  return (
    <nav aria-label="Market days" className="mt-4">
      <ul className="flex gap-2 overflow-x-auto pb-1">
        {days.map((d) => (
          <li key={d.date} className="shrink-0">
            <Link
              href={`/markets/${d.date}`}
              aria-current={d.date === current ? "page" : undefined}
              className={`block rounded border px-3 py-2 font-sans text-sm ${
                d.date === current ? "border-ink bg-surface text-ink" : "border-line text-warm hover:bg-surface hover:text-ink"
              }`}
            >
              <span className="block font-medium">{formatDay(d.date)}</span>
              <span className="block font-mono text-xs">
                NIFTY {signedPct(d.nifty_pct)} · {regimeLabel(d.regime)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
