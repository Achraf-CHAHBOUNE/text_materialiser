import { Check, ChevronDown, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useI18n } from "@/lib/i18n";

export type FilterOption = { key: string; label: string; count?: number };

/** One filter, as a button that opens its list.
 *
 *  The lists behind these are long - 27 years, 70 cities, 250 subjects - and laying
 *  them all out at once buried the rulings under rows of chips. Behind a button they
 *  cost one click, the page keeps its shape whatever the chamber, and the list can be
 *  typed into, which matters most for the cities and the subjects.
 */
export function FilterMenu({
  label, value, options, onChange, allLabel, searchPlaceholder, align = "start", width = "16rem",
}: {
  label: string;
  value?: string | undefined;
  options: FilterOption[];
  onChange: (key: string | undefined) => void;
  allLabel: string;
  searchPlaceholder?: string;
  align?: "start" | "center" | "end";
  width?: string;
}) {
  const { t, num } = useI18n();
  const [open, setOpen] = useState(false);
  const chosen = options.find((o) => o.key === value);

  const pick = (key: string | undefined) => { onChange(key); setOpen(false); };

  return (
    <div className="inline-flex items-center">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant={chosen ? "default" : "outline"}
            size="sm"
            aria-label={label}
            className={`h-9 gap-1.5 ${chosen ? "pe-2" : ""}`}
          >
            <span className="text-muted-foreground-none opacity-70">{label}</span>
            <span className="font-medium">{chosen ? chosen.label : allLabel}</span>
            <ChevronDown className="size-3.5 opacity-60" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align={align} className="p-0" style={{ width }}>
          <Command
            // the labels are Arabic; matching on the raw string is what a reader types
            filter={(v, search) => (v.includes(search) ? 1 : 0)}
          >
            {options.length > 8 && (
              <CommandInput placeholder={searchPlaceholder ?? label} className="h-9" />
            )}
            <CommandList className="max-h-72">
              <CommandEmpty className="py-4 text-center text-xs">
                {t("listing.noMatch")}
              </CommandEmpty>
              <CommandGroup>
                <CommandItem value={allLabel} onSelect={() => pick(undefined)}>
                  <Check className={`size-4 ${value ? "opacity-0" : "opacity-100"}`} aria-hidden />
                  <span className="flex-1">{allLabel}</span>
                </CommandItem>
                {options.map((o) => (
                  <CommandItem key={o.key} value={o.label} onSelect={() => pick(o.key)}>
                    <Check
                      className={`size-4 ${value === o.key ? "opacity-100" : "opacity-0"}`}
                      aria-hidden
                    />
                    <span className="flex-1 truncate">{o.label}</span>
                    {o.count !== undefined && (
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {num(o.count)}
                      </span>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {chosen && (
        <button
          type="button"
          onClick={() => onChange(undefined)}
          aria-label={`${t("listing.clear")} ${label}`}
          className="-ms-px inline-flex size-9 items-center justify-center rounded-e-md border border-s-0 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}
