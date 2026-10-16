// The component that streams and displays a debate.
import { DebateStream } from "@/components/DebateStream";
// The site header.
import { Header } from "@/components/Header";

// The home page (address "/"): shows the most recent debate.
export default function HomePage() {
  return (
    // The page's main content area with space at the bottom.
    <main className="pb-16">
      {/* Title and navigation. */}
      <Header />
      <div className="mt-8">
        {/* "latest" tells the server to pick the newest stored debate. */}
        <DebateStream debateId="latest" />
      </div>
    </main>
  );
}
