"use client";

export type Topic = { id: string; label: string };

export function TopicTabs({
  topics,
  activeId,
  onSelect,
}: {
  topics: Topic[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="flex gap-8 border-b border-line">
      {topics.map((topic) => {
        const active = topic.id === activeId;
        return (
          <button
            key={topic.id}
            onClick={() => onSelect(topic.id)}
            className={`relative pb-3 font-sans text-sm ${active ? "font-medium text-ink" : "text-warm"}`}
          >
            {topic.label}
            <span
              className={`tab-underline absolute bottom-0 left-0 h-[2px] bg-ink ${active ? "w-full" : "w-0"}`}
            />
          </button>
        );
      })}
    </nav>
  );
}
