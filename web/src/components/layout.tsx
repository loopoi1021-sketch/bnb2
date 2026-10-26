import { useEffect, useState } from "react"
import { FileText, FlaskConical, Inbox, LayoutDashboard, MessagesSquare, Monitor, Moon, Sun } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useApi } from "@/lib/api"

const NAV = [
  { to: "/", label: "개요", icon: LayoutDashboard },
  { to: "/inbox", label: "처리함", icon: Inbox },
  { to: "/conversations", label: "대화", icon: MessagesSquare },
  { to: "/evals", label: "시험", icon: FlaskConical },
  { to: "/docs", label: "문서", icon: FileText },
]

type Theme = "light" | "dark" | "system"

function readTheme(): Theme {
  try {
    return (localStorage.getItem("theme") as Theme) || "system"
  } catch {
    return "system"
  }
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const apply = () =>
      document.documentElement.classList.toggle("dark", theme === "dark" || (theme === "system" && media.matches))
    apply()
    media.addEventListener("change", apply)
    try {
      localStorage.setItem("theme", theme)
    } catch {
      /* 저장이 안 돼도 이번 화면에는 적용된다 */
    }
    return () => media.removeEventListener("change", apply)
  }, [theme])
  return [theme, setTheme] as const
}

export function Layout() {
  const [theme, setTheme] = useTheme()
  const { pathname } = useLocation()
  const pending = useApi<{ open: number }>("/api/inbox/count").data?.open
  const current = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to)))

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
              b2
            </div>
            <div className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
              <div className="truncate text-sm font-semibold">bnb2 운영</div>
              <div className="truncate text-xs text-muted-foreground">사내 문서 Q&A 봇</div>
            </div>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map((n) => (
                  <SidebarMenuItem key={n.to}>
                    <SidebarMenuButton asChild isActive={n === current} tooltip={n.label}>
                      <NavLink to={n.to}>
                        <n.icon />
                        <span>{n.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                    {n.to === "/inbox" && !!pending && (
                      <SidebarMenuBadge aria-label={`처리 대기 ${pending}건`}>{pending}</SidebarMenuBadge>
                    )}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="group-data-[collapsible=icon]:hidden">
          <ToggleGroup
            type="single"
            size="sm"
            variant="outline"
            value={theme}
            onValueChange={(v) => v && setTheme(v as Theme)}
            aria-label="화면 테마"
            className="w-full"
          >
            <ToggleGroupItem value="light" aria-label="라이트" className="flex-1">
              <Sun />
            </ToggleGroupItem>
            <ToggleGroupItem value="system" aria-label="시스템 설정" className="flex-1">
              <Monitor />
            </ToggleGroupItem>
            <ToggleGroupItem value="dark" aria-label="다크" className="flex-1">
              <Moon />
            </ToggleGroupItem>
          </ToggleGroup>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-12 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur">
          <SidebarTrigger className="-ml-1" />
          <span className="text-sm text-muted-foreground">bnb2</span>
          <span className="text-sm text-muted-foreground">/</span>
          <span className="text-sm font-medium">{current?.label}</span>
        </header>
        <div className="mx-auto w-full max-w-[1400px] p-6">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
