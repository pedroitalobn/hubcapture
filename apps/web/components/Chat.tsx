/**
 * Peças compartilhadas do chat (Copiloto + onboarding conversacional):
 * bolhas com entrada animada e indicador de digitação em três pontos.
 * O movimento vem das classes do design system (globals.css).
 */

export function ChatBubble({
  autor,
  children,
}: {
  autor: "user" | "ai";
  children: React.ReactNode;
}) {
  if (autor === "user") {
    return <div className="bubble bubble-user">{children}</div>;
  }
  return (
    <div className="flex max-w-[85%] items-end gap-2 self-start">
      <span className="brand-dot brand-dot-pulse mb-3 shrink-0" aria-hidden />
      <div className="bubble bubble-ai !max-w-full">{children}</div>
    </div>
  );
}

export function TypingDots() {
  return (
    <div className="flex max-w-[85%] items-end gap-2 self-start">
      <span className="brand-dot brand-dot-pulse mb-3 shrink-0" aria-hidden />
      <div
        className="bubble bubble-ai flex items-center gap-1.5 py-3.5"
        aria-label="Copiloto digitando"
      >
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  );
}
