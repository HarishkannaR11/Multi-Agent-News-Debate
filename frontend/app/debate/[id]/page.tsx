import { DebateStream } from "@/components/DebateStream";
import { Header } from "@/components/Header";

export default function DebatePage({ params }: { params: { id: string } }) {
  return (
    <main className="pb-16">
      <Header date={params.id} topicCount={1} />
      <div className="mt-8">
        <DebateStream debateId={params.id} />
      </div>
    </main>
  );
}
