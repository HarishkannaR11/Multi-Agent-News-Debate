import type { Source } from "@/lib/debate";

// Links from a claim to the sources it cites. They jump to the matching entry in the Sources list.
export function SourceChips({ ids, sources }: { ids: string[]; sources: Source[] }) {
  if (ids.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {ids.map((id) => {
        const source = sources.find((s) => s.id === id);
        return (
          <a
            key={id}
            href={`#source-${id}`}
            aria-label={`Source ${id}${source ? `: ${source.title}` : ""}`}
            className="rounded-sm border border-edge px-1.5 py-0.5 font-mono text-[11px] text-ink hover:bg-surface"
          >
            {id}
          </a>
        );
      })}
    </span>
  );
}
