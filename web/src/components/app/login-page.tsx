import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { useLogin, useNotify, useTranslate } from "@/lib/app-context";
import { KeyRound, Shield } from "lucide-react";

import { getAuthConfig, type AuthProvidersInfo } from "@/authConfig";
import { LocalesMenuButton } from "@/components/app/locales-menu-button";
import { ThemeModeToggle } from "@/components/app/theme-mode-toggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Notification } from "@/components/app/notification";
import { Badge } from "@/components/ui/badge";

export const LoginPage = (props: { redirectTo?: string }) => {
  const [searchParams] = useSearchParams();
  const redirectTo = props.redirectTo ?? searchParams.get("redirectTo") ?? "/";
  const [loading, setLoading] = useState(false);
  const [authConfig, setAuthConfig] = useState<AuthProvidersInfo | null>(null);
  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const notify = useNotify();
  const translate = useTranslate();

  useEffect(() => {
    void getAuthConfig(true).then(setAuthConfig);
  }, []);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    login(
      {
        provider: "local",
        username_or_email: usernameOrEmail,
        password,
      },
      redirectTo,
    )
      .then(() => setLoading(false))
      .catch((error) => {
        setLoading(false);
        notify(
          typeof error === "string"
            ? error
            : typeof error === "undefined" || !error.message
              ? "ra.auth.sign_in_error"
              : error.message,
          {
            type: "error",
            messageArgs: {
              _:
                typeof error === "string"
                  ? error
                  : error && error.message
                    ? error.message
                    : undefined,
            },
          },
        );
      });
  };

  const handleProxyLogin = () => {
    setLoading(true);
    login({ provider: "proxy" }, redirectTo).catch((error) => {
      setLoading(false);
      notify(error?.message || "ra.auth.sign_in_error", { type: "error" });
    });
  };

  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <header className="flex h-16 shrink-0 items-center justify-between border-b px-4 sm:h-12">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-card text-card-foreground shadow-sm">
            <Shield className="h-4 w-4" />
          </div>
          <span className="truncate text-sm font-semibold">
            {translate("custom.login.product")}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <LocalesMenuButton className="inline-flex" />
          <ThemeModeToggle />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="grid w-full max-w-5xl gap-8 lg:grid-cols-[1fr_420px] lg:items-center">
          <section className="space-y-5">
            <Badge variant="secondary" className="w-fit">
              {translate("custom.login.workspace_badge")}
            </Badge>
            <div className="space-y-3">
              <h1 className="max-w-2xl text-3xl font-semibold leading-tight tracking-normal sm:text-4xl">
                {translate("custom.login.title")}
              </h1>
              <p className="max-w-xl text-sm leading-6 text-muted-foreground sm:text-base">
                {translate("custom.login.description")}
              </p>
            </div>
          </section>

          <Card className="w-full shadow-sm">
            <CardHeader>
              <CardTitle>{translate("custom.login.card_title")}</CardTitle>
              <CardDescription>{translate("custom.login.card_description")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {authConfig?.local_enabled ? (
                <form className="space-y-4" onSubmit={handleSubmit}>
                  <div className="space-y-2">
                    <Label htmlFor="username_or_email">
                      {translate("custom.login.username_or_email")}
                    </Label>
                    <Input
                      id="username_or_email"
                      name="username_or_email"
                      value={usernameOrEmail}
                      onChange={(event) => setUsernameOrEmail(event.target.value)}
                      autoComplete="username"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">{translate("custom.login.password")}</Label>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </div>
                  <Button type="submit" className="w-full cursor-pointer" disabled={loading}>
                    <KeyRound className="h-4 w-4" />
                    {loading
                      ? translate("custom.login.signing_in")
                      : translate("custom.login.sign_in")}
                  </Button>
                </form>
              ) : null}

              {authConfig?.proxy_enabled ? (
                <Button
                  type="button"
                  variant={authConfig.local_enabled ? "outline" : "default"}
                  className="w-full cursor-pointer"
                  disabled={loading}
                  onClick={handleProxyLogin}
                >
                  <Shield className="h-4 w-4" />
                  {translate("custom.login.sign_in_sso")}
                </Button>
              ) : null}

              {authConfig?.load_error ? (
                <p className="text-sm text-muted-foreground">
                  {translate("custom.login.provider_load_error")}
                </p>
              ) : null}

              {authConfig &&
              !authConfig.load_error &&
              !authConfig.local_enabled &&
              !authConfig.proxy_enabled ? (
                <p className="text-sm text-muted-foreground">
                  {translate("custom.login.no_provider")}
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </main>
      <Notification />
    </div>
  );
};
