import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { Layout } from "@/components/layout"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Conversations } from "@/pages/conversations"
import { Docs } from "@/pages/docs"
import { Evals } from "@/pages/evals"
import { Inbox } from "@/pages/inbox"
import { OverviewPage } from "@/pages/overview"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TooltipProvider delayDuration={150}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<OverviewPage />} />
            <Route path="inbox" element={<Inbox />} />
            <Route path="conversations" element={<Conversations />} />
            <Route path="evals" element={<Evals />} />
            <Route path="docs" element={<Docs />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </StrictMode>,
)
