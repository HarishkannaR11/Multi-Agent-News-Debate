// Runs in the browser: loads the day, keeps it fresh while it is being generated, and holds the selected analyst.
"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import { formatDay } from "@/lib/debate";
import {
  fetchMarketDay,
  isMarketGenerating,
  latestOf,
  MARKET_ROLES,
  marketStatusLabel,
  regimeLabel,
  signedPct,
  stageText,
  type MarketDay,
  type MarketRole,
} from "@/lib/markets";
import { readTab, writeTab } from "@/lib/storage";
import { AgentsSection } from "./AgentsSection";
import { AttributionPanel } from "./AttributionPanel";
import { DayPicker } from "./DayPicker";
import { FactsSection } from "./FactsSection";
import { SeriesTable } from "./SeriesTable";
import { VerdictCard } from "./VerdictCard";

const POLL_MS = 2500;
const POLL_MAX_MS = 10_000;

function isRole(value: string | null): value is MarketRole {
  return MARKET_ROLES.includes(value as MarketRole);
}

// The whole market-day page below the header. "date" may be "latest".
export function MarketView({ date }: { date: string }) {
  const [day, setDay] = useState<MarketDay | null>(null);
  const [loadError, setLoadError] = useState<{ status: number; message: string } | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MarketRole>("bull");
  const [reloadKey, setReloadKey] = useState(0);
  const [chosen, setChosen] = useState(false);

  // Load, then poll while generating. Everything is cancelled when the date changes.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let target = date;
    let loaded = false;
    let wasGenerating = false;
    setDay(null);
    setLoadError(null);
    setPollError(null);
    setChosen(false);

    const tick = async () => {
      try {
        const next = await fetchMarketDay(target);
        if (cancelled) return;
        target = next.date;
        loaded = true;
        failures = 0;
        wasGenerating = isMarketGenerating(next);
        setPollError(null);
        setDay(next);
        if (wasGenerating) timer = setTimeout(tick, POLL_MS);
      } catch (err) {
        if (cancelled) return;
        failures += 1;
        const status = err instanceof ApiError ? err.status : 0;
        const message = err instanceof Error ? err.message : "Failed to load the market day";
        if (!loaded) {
          setLoadError({ status, message });
          return;
        }
        setPollError(message);
        if (wasGenerating && status !== 404) timer = setTimeout(tick, Math.min(POLL_MS * 2 ** failures, POLL_MAX_MS));
      }
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [date, reloadKey]);

  // Pick the first analyst tab once: the last one read, else the first that finished.
  useEffect(() => {
    if (!day || chosen) return;
    setChosen(true);
    const saved = readTab(`market:${day.date}`);
    const firstDone = MARKET_ROLES.find((r) => day.agents[r].status === "completed");
    setSelected(isRole(saved) ? saved : (firstDone ?? "bull"));
    document.title = `Market debate ${day.date} · The Debate`;
  }, [day, chosen]);

  const nifty = useMemo(() => {
    const series = day?.packet.series.NIFTY50;
    return series ? latestOf(series) : null;
  }, [day]);

  if (loadError && !day) {
    const missing = loadError.status === 404;
    const off = loadError.status === 503;
    return (
      <div role="alert" className="mt-16 max-w-reading">
        <h1 className="font-serif text-3xl font-semibold text-ink">
          {missing ? "No market day here" : off ? "Markets are switched off" : "Could not load the market day"}
        </h1>
        <p className="mt-3 font-sans text-base text-warm">
          {missing
            ? date === "latest"
              ? "No market day has been generated yet. The first one is created after the Indian close on a trading day."
              : "That market day does not exist."
            : loadError.message}
        </p>
        <div className="mt-6 flex flex-wrap gap-3 font-sans text-sm">
          {!missing && !off && (
            <button type="button" onClick={() => setReloadKey((n) => n + 1)} className="rounded border border-edge px-4 py-2 text-ink hover:bg-surface">
              Retry
            </button>
          )}
          <Link href="/" className="rounded border border-edge px-4 py-2 text-ink hover:bg-surface">
            News debate
          </Link>
        </div>
      </div>
    );
  }

  if (!day) {
    return (
      <div role="status" aria-label="Loading the market day" className="mt-10 space-y-4">
        <div className="skeleton h-4 w-40 rounded bg-line" />
        <div className="skeleton h-10 w-3/4 rounded bg-line" />
        <div className="skeleton h-4 w-full max-w-reading rounded bg-line" />
      </div>
    );
  }

  const generating = isMarketGenerating(day);
  const analysts = MARKET_ROLES.filter((r) => day.agents[r].status === "completed").length;
  const packet = day.packet;
  const moved = packet.requested_date !== packet.as_of;

  return (
    <article className="pb-16">
      <header id="overview" className="mt-6">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-sm text-muted">
          <span>Market day</span>
          <span aria-hidden="true">·</span>
          <span className={`rounded-sm border px-1.5 py-0.5 text-xs font-medium ${day.status === "done" ? "border-ok text-ok" : "border-warn text-warn"}`}>
            {marketStatusLabel(day)}
          </span>
          <span className="rounded-sm border border-edge px-1.5 py-0.5 text-xs font-medium text-ink">{regimeLabel(packet.regime.label)}</span>
        </p>
        <h1 className="mt-3 font-serif text-4xl font-bold leading-[1.15] tracking-[-0.02em] text-ink md:text-5xl">{formatDay(packet.as_of)}</h1>
        {nifty && (
          <p className="mt-3 font-sans text-lg text-warm">
            NIFTY 50 closed at <strong className="text-ink">{nifty.value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong>,{" "}
            <strong className="text-ink">{signedPct(nifty.changePct)}</strong> on the day.
          </p>
        )}
        {moved && (
          <p className="mt-2 font-sans text-sm text-muted">
            Requested {formatDay(packet.requested_date)}; showing the last trading day, {formatDay(packet.as_of)}.
          </p>
        )}
        <p className="mt-4 max-w-reading font-sans text-sm text-muted">
          AI analysts debate a frozen data snapshot. Their claims must cite the numbered facts below and are checked by code; this is commentary
          on data, not investment advice.
        </p>
        <DayPicker current={day.date} />
      </header>

      <div className="mt-8 space-y-10">
        {(generating || pollError) && (
          <section aria-label="Generation status" className="rounded border border-line bg-surface p-4">
            {generating && (
              <div role="status" aria-live="polite">
                <p className="font-sans text-base font-medium text-ink">{stageText(day.stage)}</p>
                <p className="mt-1 font-sans text-sm text-muted">This page updates by itself.</p>
              </div>
            )}
            {pollError && (
              <p role="alert" className="mt-3 font-sans text-sm text-warn">
                {pollError} We keep trying; what you see may be out of date.
              </p>
            )}
          </section>
        )}
        <SeriesTable series={packet.series} />
        <AttributionPanel attribution={packet.attribution} regime={packet.regime} />
        <AgentsSection
          agents={day.agents}
          selected={selected}
          onSelect={(role) => {
            setSelected(role);
            writeTab(`market:${day.date}`, role);
          }}
        />
        <VerdictCard verdict={day.verdict} error={day.verdict_error} generating={generating} analysts={analysts} />
        <FactsSection facts={packet.facts} sha={day.packet_sha256} />
      </div>
    </article>
  );
}
