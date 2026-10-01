import { DebateStream } from "@/components/DebateStream";
import { Header } from "@/components/Header";

export default function DebatePage({ params }: { params: { id: string } }) {
  // Ids look like "2026-09-30:some-topic"; the ':' may arrive percent-encoded.
  let id = params.id;
  try {
    id = decodeURIComponent(params.id);
  } catch {
    // malformed escape: use it as-is and let the API answer 404
  }
  const date = id.split(":")[0];

  return (
    <main className="pb-16">
      <Header date={date} />
      <div className="mt-8">
        <DebateStream debateId={id} />
      </div>
    </main>
  );
}
