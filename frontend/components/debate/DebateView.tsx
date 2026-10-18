// Runs in the browser: it loads the debate, keeps it fresh while it is being generated, and holds the page's shared state.
"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchDebate, retryDebate, type Debate } from "@/lib/api";
import {
  claimIndex,
  completedCount,
  formatDay,
  isGenerating,
  isStructured,
  PERSONAS,
  perspectiveViews,
  safeHttpUrl,
  statusLabel,
  type Persona,
  type Verdict,
} from "@/lib/debate";
import { readTab, writeTab } from "@/lib/storage";
import { OpinionBox } from "../OpinionBox";
import { DebateActions } from "./DebateActions";
import { DisagreementMap } from "./DisagreementMap";
import { FeedbackForm } from "./FeedbackForm";
import { FollowUp } from "./FollowUp";
import { GenerationStatus } from "./GenerationStatus";
import { PerspectiveExplorer } from "./PerspectiveExplorer";
import { SourcesSection } from "./SourcesSection";
import { VerdictSection } from "./VerdictSection";

// How often to ask the server for progress while a debate is generating (longer after failures).
const POLL_MS = 2000;
const POLL_MAX_MS = 10_000;

function isPersona(value: string | null | undefined): value is Persona {
  return PERSONAS.includes(value as Persona);
}

// The whole debate page below the header. "debateId" may be "latest".
export function DebateView({ debateId }: { debateId: string }) {
  const [debate, setDebate] = useState<Debate | null>(null);
  const [loadError, setLoadError] = useState<{ status: number; message: string } | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Persona>("left");
  const [retrying, setRetrying] = useState<Set<string>>(new Set());
  const [reloadKey, setReloadKey] = useState(0);
  // The claim a link asked for; it is scrolled to once its tab is on screen.
  const [pendingClaim, setPendingClaim] = useState<string | null>(null);
  const tabChosen = useRef(false);

  // Loads the debate, then polls while it is generating. Everything is cancelled when the debate id changes.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let target = debateId;
    // Whether a first answer arrived, and whether the last answer said "generating" (so a failed refresh should try again).
    let loaded = false;
    let wasGenerating = false;
    setDebate(null);
    setLoadError(null);
    setPollError(null);
    tabChosen.current = false;

    const tick = async () => {
      try {
        const next = await fetchDebate(target);
        if (cancelled) return;
        // After the first answer, "latest" is replaced by the real id so later polls cannot jump to a newer debate.
        target = next.id;
        loaded = true;
        failures = 0;
        wasGenerating = isGenerating(next);
        setPollError(null);
        setDebate(next);
        if (wasGenerating) timer = setTimeout(tick, POLL_MS);
      } catch (err) {
        if (cancelled) return;
        failures += 1;
        const status = err instanceof ApiError ? err.status : 0;
        const message = err instanceof Error ? err.message : "Failed to load the debate";
        // A failed first load is an error page; a failed refresh keeps showing what we have, with a notice.
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
  }, [debateId, reloadKey]);

  const views = useMemo(() => (debate ? perspectiveViews(debate) : []), [debate]);
  const index = useMemo(() => claimIndex(views), [views]);
  const structured = debate ? isStructured(debate) : false;
  const sources = useMemo(() => debate?.sources ?? [], [debate]);
  const validRefs = useMemo(() => new Set([...index.keys(), ...sources.map((s) => s.id)]), [index, sources]);

  // The browser tab shows the question.
  useEffect(() => {
    if (debate) document.title = `${debate.question || debate.topic} · The Debate`;
  }, [debate]);

  // Choose the first tab once: a #claim-… link, else the last tab read, else the first finished analyst.
  useEffect(() => {
    if (!debate || tabChosen.current) return;
    tabChosen.current = true;
    const hash = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    const fromHash = hash.startsWith("claim-") ? hash.slice(6).split("-")[0] : null;
    const saved = readTab(debate.id);
    const firstDone = views.find((v) => v.state === "completed")?.persona;
    const choice = isPersona(fromHash) ? fromHash : isPersona(saved) ? saved : (firstDone ?? "left");
    setSelected(choice);
    if (isPersona(fromHash)) setPendingClaim(hash.slice(6));
  }, [debate, views]);

  const select = useCallback(
    (persona: Persona) => {
      setSelected(persona);
      if (debate) writeTab(debate.id, persona);
    },
    [debate]
  );

  // Switches to the analyst who made the claim, then scrolls to it and puts the address in the bar.
  const jumpToClaim = useCallback(
    (claimId: string) => {
      const persona = claimId.split("-")[0];
      if (isPersona(persona)) select(persona);
      setPendingClaim(claimId);
    },
    [select]
  );
  useEffect(() => {
    if (!pendingClaim) return;
    const element = document.getElementById(`claim-${pendingClaim}`);
    if (!element) return;
    window.history.replaceState(null, "", `#claim-${pendingClaim}`);
    element.scrollIntoView({ block: "center" });
    element.setAttribute("tabindex", "-1");
    element.focus({ preventScroll: true });
    setPendingClaim(null);
  }, [pendingClaim, selected, debate]);

  async function retry(persona?: Persona) {
    if (!debate) return;
    const key = persona ?? "all";
    setActionError(null);
    setRetrying((prev) => new Set(prev).add(key));
    try {
      await retryDebate(debate.id, persona);
      // Reload: the debate is "generating" again, so polling resumes by itself.
      setReloadKey((n) => n + 1);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not retry. Try again.");
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  if (loadError && !debate) {
    const missing = loadError.status === 404;
    return (
      <div role="alert" className="mt-16 max-w-reading">
        <h1 className="font-serif text-3xl font-semibold text-ink">{missing ? "No debate here" : "Could not load the debate"}</h1>
        <p className="mt-3 font-sans text-base text-warm">
          {missing
            ? debateId === "latest"
              ? "No daily debate has been published yet. You can start your own."
              : "This debate does not exist, or its address is wrong."
            : loadError.message}
        </p>
        <div className="mt-6 flex flex-wrap gap-3 font-sans text-sm">
          {!missing && (
            <button type="button" onClick={() => setReloadKey((n) => n + 1)} className="rounded border border-edge px-4 py-2 text-ink hover:bg-surface">
              Retry
            </button>
          )}
          <Link href="/new" className="rounded bg-ink px-4 py-2 font-medium text-paper hover:opacity-90">
            Start a debate
          </Link>
          <Link href="/archive" className="rounded border border-edge px-4 py-2 text-ink hover:bg-surface">
            Browse the archive
          </Link>
        </div>
      </div>
    );
  }

  if (!debate) {
    return (
      <div role="status" aria-label="Loading the debate" className="mt-10 space-y-4">
        <div className="skeleton h-4 w-40 rounded bg-line" />
        <div className="skeleton h-10 w-3/4 rounded bg-line" />
        <div className="skeleton h-4 w-full max-w-reading rounded bg-line" />
        <div className="skeleton h-4 w-5/6 max-w-reading rounded bg-line" />
      </div>
    );
  }

  const generating = isGenerating(debate);
  const done = completedCount(views);
  const failed = views.filter((v) => v.state === "failed").length;
  const claimCount = index.size;
  const title = debate.question || debate.topic;
  const verdictData = debate.verdict_data as Partial<Verdict> | undefined;
  const summary = verdictData?.summary || (structured ? "" : debate.verdict);
  const centralQuestion = debate.disagreements?.central_question;
  const sourceHref = debate.source_url ? safeHttpUrl(debate.source_url) : null;
  const enoughForMap = done >= 3;

  return (
    <article className="pb-16">
      <DebateActions debateId={debate.id} title={title} />

      <header id="overview" className="mt-6">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-sm text-muted">
          <span>{formatDay(debate.created_at || debate.date)}</span>
          <span aria-hidden="true">·</span>
          <span>{debate.category || (debate.origin === "user" ? "Uncategorised" : "Daily debate")}</span>
          <span aria-hidden="true">·</span>
          <span className={`rounded-sm border px-1.5 py-0.5 text-xs font-medium ${debate.status === "done" ? "border-ok text-ok" : "border-warn text-warn"}`}>
            {statusLabel(debate, views)}
          </span>
        </p>
        <h1 className="mt-3 max-w-[28ch] font-serif text-4xl font-bold leading-[1.15] tracking-[-0.02em] text-ink md:text-5xl">{title}</h1>
        {summary && <p className="mt-4 max-w-reading font-sans text-lg leading-relaxed text-warm">{summary}</p>}
        {centralQuestion && (
          <p className="mt-4 max-w-reading font-serif text-xl italic leading-snug text-ink">
            <span className="mr-2 font-sans text-xs not-italic uppercase tracking-[0.06em] text-muted">Central question</span>
            {centralQuestion}
          </p>
        )}
        <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-2 font-sans text-sm text-warm">
          <div>
            <dt className="inline text-muted">Perspectives </dt>
            <dd className="inline font-medium text-ink">
              {done} of {views.length}
            </dd>
          </div>
          {structured && (
            <>
              <div>
                <dt className="inline text-muted">Claims </dt>
                <dd className="inline font-medium text-ink">{claimCount}</dd>
              </div>
              <div>
                <dt className="inline text-muted">Sources </dt>
                <dd className="inline font-medium text-ink">{sources.length}</dd>
              </div>
            </>
          )}
          {sourceHref && (
            <div>
              <dt className="inline text-muted">Original article </dt>
              <dd className="inline">
                <a href={sourceHref} target="_blank" rel="noopener noreferrer nofollow" className="underline underline-offset-2">
                  open<span className="sr-only"> (opens in a new tab)</span>
                </a>
              </dd>
            </div>
          )}
        </dl>
        {structured && debate.origin === "user" && (
          <p className="mt-4 max-w-reading font-sans text-sm text-muted">
            Written by AI analysts from your question{debate.use_sources ? " and related news coverage" : ""}. Claims are labelled by type and are not
            fact-checked. This page is unlisted: only people with the link can find it.
          </p>
        )}
      </header>

      <div className="mt-6 space-y-10">
        <GenerationStatus
          debate={debate}
          views={views}
          failedCount={failed}
          retrying={retrying.has("all")}
          onRetryAll={() => void retry()}
          pollError={pollError}
        />
        {actionError && (
          <p role="alert" className="font-sans text-sm text-agents-left">
            {actionError}
          </p>
        )}

        <PerspectiveExplorer
          views={views}
          selected={selected}
          onSelect={select}
          sources={sources}
          disagreements={debate.disagreements}
          retrying={retrying}
          onRetry={(persona) => void retry(persona)}
        />

        {structured && (
          <DisagreementMap
            disagreements={debate.disagreements}
            index={index}
            sources={sources}
            enough={enoughForMap}
            generating={generating}
            onRetry={() => void retry()}
          />
        )}

        <VerdictSection
          debate={debate}
          views={views}
          structured={structured}
          generating={generating}
          retrying={retrying.has("all")}
          onRetry={() => void retry()}
          onJumpToClaim={jumpToClaim}
          validRefs={validRefs}
        />

        {structured && <SourcesSection sources={sources} index={index} searched={Boolean(debate.use_sources)} onJumpToClaim={jumpToClaim} />}

        {structured && <FollowUp debateId={debate.id} disabled={generating || done === 0} validRefs={validRefs} onJumpToClaim={jumpToClaim} />}

        {!generating && (
          <div className="border-t border-line">
            <OpinionBox debateId={debate.id} />
          </div>
        )}

        {!generating && structured && <FeedbackForm debateId={debate.id} />}
      </div>
    </article>
  );
}
