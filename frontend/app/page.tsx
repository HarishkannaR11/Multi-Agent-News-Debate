import { DebateStream } from "@/components/DebateStream";
import { Header } from "@/components/Header";

export default function HomePage() {
  const displayDate = new Date().toLocaleDateString("en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <main className="pb-16">
      <Header date={displayDate} topicCount={1} />
      <div className="mt-8">
        <DebateStream debateId="latest" />
      </div>
    </main>
  );
}
