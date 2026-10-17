// The component that streams and displays a debate.
import { DebateStream } from "@/components/DebateStream";
// The site header.
import { Header } from "@/components/Header";

// The page for one specific debate (address "/debate/<id>"); Next.js passes the <id> part in "params".
// Since Next.js 15, "params" is a Promise, so the page is an async function that waits for it.
export default async function DebatePage({ params }: { params: Promise<{ id: string }> }) {
  // Wait for the route parameters and take the raw <id> from the address.
  const { id: rawId } = await params;
  // Ids look like "2026-09-30:some-topic"; the ':' may arrive percent-encoded.
  // Start with the raw value from the address.
  let id = rawId;
  try {
    // Turn "%3A" back into ":".
    id = decodeURIComponent(rawId);
  } catch {
    // malformed escape: use it as-is and let the API answer 404
  }
  // The date is the part before the ":"; it is shown in the header.
  const date = id.split(":")[0];

  return (
    <main className="pb-16">
      {/* Header with the date shown at the top right. */}
      <Header date={date} />
      <div className="mt-8">
        {/* Stream this specific debate. */}
        <DebateStream debateId={id} />
      </div>
    </main>
  );
}
