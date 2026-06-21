import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useLocales, useLocaleState, useTranslate } from "@/lib/app-context";

export function LocalesMenuButton({ className }: { className?: string }) {
  const languages = useLocales();
  const [locale, setLocale] = useLocaleState();
  const translate = useTranslate();

  const getNameForLocale = (locale: string): string => {
    const language = languages.find((language) => language.locale === locale);
    return language ? language.name : "";
  };

  const changeLocale = (locale: string) => (): void => {
    setLocale(locale);
  };

  if (languages.length <= 1) {
    return null;
  }
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn("hidden sm:inline-flex", className)}
          aria-label={translate("custom.language")}
          title={translate("custom.language")}
        >
          {locale.toUpperCase()}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {languages.map((language) => (
          <DropdownMenuItem key={language.locale} onClick={changeLocale(language.locale)}>
            {getNameForLocale(language.locale)}
            <Check className={cn("ml-auto", locale !== language.locale && "hidden")} />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
