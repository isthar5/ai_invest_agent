import { useState, useEffect } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  /** External value — fills input when a suggested question is clicked */
  value?: string;
}

export function ChatInput({ onSend, disabled = false, value }: ChatInputProps) {
  const [internalValue, setInternalValue] = useState("");

  // Sync external value into input (question click)
  useEffect(() => {
    if (value !== undefined) {
      setInternalValue(value);
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = internalValue.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setInternalValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSend();
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Input
        value={internalValue}
        onChange={(e) => setInternalValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入想要分析的问题，或点击上方推荐问题..."
        disabled={disabled}
        className="h-10 flex-1"
      />
      <Button
        type="button"
        size="default"
        disabled={disabled || !internalValue.trim()}
        onClick={handleSend}
        className={cn("shrink-0 gap-1.5")}
      >
        <Send className="h-4 w-4" aria-hidden="true" />
        发送
      </Button>
    </div>
  );
}
