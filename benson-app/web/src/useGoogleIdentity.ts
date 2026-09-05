import { useEffect, useRef } from "react";
import type { RequestStatus } from "./types";

type GoogleIdentity = {
  accounts: {
    id: {
      initialize(options: { client_id: string; callback(response: { credential: string }): void }): void;
      renderButton(element: HTMLElement, options: Record<string, string>): void;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

export function useGoogleIdentity(
  requestStatus: RequestStatus,
  onCredential: (credential: string) => void,
  onUnavailable: () => void,
) {
  const googleButton = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (requestStatus !== "auth-required" || !googleButton.current) return;
    fetch("/api/benson/v1/auth/config")
      .then((response) => response.json())
      .then((config: { client_id: string }) => {
        if (!config.client_id) return;
        const render = () => {
          if (!window.google || !googleButton.current) return;
          window.google.accounts.id.initialize({
            client_id: config.client_id,
            callback: ({ credential }) => onCredential(credential),
          });
          window.google.accounts.id.renderButton(googleButton.current, {
            theme: "outline",
            size: "large",
            text: "signin_with",
          });
        };
        if (window.google) return render();
        const script = document.createElement("script");
        script.src = "https://accounts.google.com/gsi/client";
        script.async = true;
        script.onload = render;
        document.head.append(script);
      })
      .catch(onUnavailable);
  }, [onCredential, onUnavailable, requestStatus]);
  return googleButton;
}
