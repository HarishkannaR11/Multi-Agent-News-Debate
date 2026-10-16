// Marks this file as a client component: it runs in the browser because it handles clicks.
"use client";

// One tab: an id to identify it and a label to display.
export type Topic = { id: string; label: string };

// A row of tabs for switching between topics (currently not used by any page).
export function TopicTabs({
  topics,
  activeId,
  onSelect,
}: {
  // The tabs to show.
  topics: Topic[];
  // The id of the currently selected tab.
  activeId: string;
  // Function called with a tab's id when the user clicks it.
  onSelect: (id: string) => void;
}) {
  return (
    // A navigation bar with a thin line underneath and space between tabs.
    <nav className="flex gap-8 border-b border-line">
      {/* Make one button per topic. */}
      {topics.map((topic) => {
        // Is this the selected tab?
        const active = topic.id === activeId;
        return (
          // Clicking tells the parent which tab was chosen; the selected tab is bold and dark.
          <button
            key={topic.id}
            onClick={() => onSelect(topic.id)}
            className={`relative pb-3 font-sans text-sm ${active ? "font-medium text-ink" : "text-warm"}`}
          >
            {/* The tab's visible text. */}
            {topic.label}
            {/* An underline bar: full width when selected, zero width (hidden) otherwise; it animates between the two. */}
            <span
              className={`tab-underline absolute bottom-0 left-0 h-[2px] bg-ink ${active ? "w-full" : "w-0"}`}
            />
          </button>
        );
      })}
    </nav>
  );
}
