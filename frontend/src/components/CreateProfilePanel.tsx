import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { languageLabel, SUPPORTED_LANGUAGES } from "@/lib/sections";

interface CreateProfilePanelProps {
  onCreateClick: (name: string, language: string) => void;
  busy: boolean;
}

// Version 4, Phase 4.6 (3.2.2) — the second profile-creation path
// alongside file-upload/paste ingestion (IngestPanel.tsx): no resume text
// to detect a language from, so it's an explicit dropdown here instead —
// matches the "language is fixed per-profile, set at creation" decision
// (docs/development_plan.md's Version 4 section) the same way ingestion's
// LLM-detected language does.
export function CreateProfilePanel({ onCreateClick, busy }: CreateProfilePanelProps) {
  const [name, setName] = useState("");
  const [language, setLanguage] = useState(SUPPORTED_LANGUAGES[0]);

  return (
    <div className="space-y-1">
      <label htmlFor="new-profile-name" className="text-sm font-medium">
        Name
      </label>
      <div className="flex items-center gap-2">
        <Input
          id="new-profile-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Candidate name"
          disabled={busy}
          className="max-w-xs"
        />
        <Select value={language} onValueChange={setLanguage} disabled={busy}>
          <SelectTrigger id="new-profile-language" aria-label="Language" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUPPORTED_LANGUAGES.map((code) => (
              <SelectItem key={code} value={code}>
                {languageLabel(code)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button type="button" onClick={() => onCreateClick(name, language)} disabled={busy}>
          Create Profile
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Starts a blank profile in the chosen language — add experience, skills, and the rest by hand.
      </p>
    </div>
  );
}
