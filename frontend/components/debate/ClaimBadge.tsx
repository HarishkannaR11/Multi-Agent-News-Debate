import { CLAIM_LABELS, claimExplanation, type Claim } from "@/lib/debate";

// Border and text colours per label. The word itself always carries the meaning (never colour alone).
const STYLE: Record<Claim["status"], string> = {
  opinion: "border-edge text-warm",
  assumption: "border-edge text-warm",
  unverified: "border-warn text-warn",
  disputed: "border-agents-left text-agents-left",
  verified: "border-ok text-ok",
};

// A small label saying what kind of claim this is and how far it can be trusted.
export function ClaimBadge({ claim }: { claim: Claim }) {
  return (
    <span
      title={claimExplanation(claim)}
      className={`inline-block shrink-0 rounded-sm border px-1.5 py-0.5 font-sans text-[11px] font-medium uppercase tracking-[0.04em] ${STYLE[claim.status]}`}
    >
      {CLAIM_LABELS[claim.status]}
    </span>
  );
}

// The legend that explains the labels; shown once, collapsed, above the claims.
export function ClaimLegend() {
  const samples: Claim[] = [
    { id: "x", text: "", type: "factual", status: "unverified", source_ids: [] },
    { id: "x", text: "", type: "factual", status: "disputed", source_ids: [] },
    { id: "x", text: "", type: "opinion", status: "opinion", source_ids: [] },
    { id: "x", text: "", type: "assumption", status: "assumption", source_ids: [] },
  ];
  return (
    <details className="rounded border border-line bg-surface p-3 font-sans text-sm text-warm">
      <summary className="cursor-pointer font-medium text-ink">How to read the claim labels</summary>
      <ul className="mt-3 space-y-2">
        {samples.map((claim) => (
          <li key={claim.status} className="flex items-start gap-3">
            <ClaimBadge claim={claim} />
            <span>{claimExplanation(claim)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3">
        No claim is ever shown as <strong className="text-ink">verified</strong>: the app has no fact-checking step. A source chip such as S1 means
        the analyst pointed at that related article, not that the article proves the claim.
      </p>
    </details>
  );
}
