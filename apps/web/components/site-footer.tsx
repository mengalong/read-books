"use client";

import { Link2 } from "lucide-react";
import { useEffect, useState } from "react";

import { getSiteFooterConfiguration } from "@/lib/api";
import type { SiteFooterConfiguration } from "@/lib/types";

export function SiteFooter() {
  const [configuration, setConfiguration] = useState<SiteFooterConfiguration | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSiteFooterConfiguration()
      .then((data) => {
        if (!cancelled) setConfiguration(data);
      })
      .catch(() => {
        if (!cancelled) setConfiguration(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!configuration?.configuration_complete) return null;

  return (
    <footer className="site-footer">
      <a
        className="site-footer-link"
        href={configuration.record_url}
        rel="noreferrer"
        target="_blank"
      >
        <Link2 size={13} />
        <span>备案号 {configuration.record_number}</span>
      </a>
    </footer>
  );
}
