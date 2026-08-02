"use client";

import { BookOpenText, History, LibraryBig, Plus, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navigation = [
  { href: "/", label: "我的书架", icon: LibraryBig },
  { href: "/books/new", label: "添加书籍", icon: Plus },
  { href: "/settings/model", label: "模型设置", icon: Settings2 },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-layout">
      <aside className="app-sidebar">
        <Link className="brand" href="/">
          <span className="brand-mark">卷</span>
          <span>
            <span className="brand-name">回卷</span>
            <span className="brand-subtitle">把读过的书再想起来</span>
          </span>
        </Link>
        <nav className="side-nav" aria-label="主导航">
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link className={active ? "active" : ""} href={href} key={href}>
                <Icon size={17} strokeWidth={1.8} />
                {label}
              </Link>
            );
          })}
          {pathname.includes("/history") && (
            <Link className="active" href={pathname}>
              <History size={17} strokeWidth={1.8} />
              测试历史
            </Link>
          )}
        </nav>
        <div className="sidebar-note">
          <strong><BookOpenText size={13} /> 原文优先</strong>
          每道题都保留 PDF 页码与原文依据，复习时可以回到上下文。
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
