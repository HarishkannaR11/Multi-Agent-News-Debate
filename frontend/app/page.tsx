import { DebateStream } from "@/components/DebateStream";
import { Header } from "@/components/Header";

export default function HomePage() {
  return (
    <main className="pb-16">
      <Header />
      <div className="mt-8">
        <DebateStream debateId="latest" />
      </div>
    </main>
  );
}
