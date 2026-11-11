import React, { useLayoutEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Gate from "./components/Gate";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import PublicHome from "./pages/PublicHome";
import PublicMap from "./pages/PublicMap";
import News from "./pages/News";
import About from "./pages/About";
import Contact from "./pages/Contact";
import WhatToDo from "./pages/WhatToDo";
import Dashboard from "./pages/Dashboard";
import HistoricalData from "./pages/HistoricalData";
import Security from "./pages/Security";
import ReportingAnalytics from "./pages/ReportingAnalytics";

function AppRoutes() {
  const { pathname } = useLocation();
  // A new page starts at the top. Before paint, so it never shows the old
  // scroll position; a ?tab= change keeps the place, like the fade.
  useLayoutEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    // Keyed on the path alone so each new page fades in, while a tab change
    // that only touches the query string leaves the page where it is.
    <div key={pathname} className="page-transition">
    <Routes>
      {/* Public, no login required */}
      <Route path="/" element={<PublicHome />} />
      <Route path="/map" element={<PublicMap />} />
      <Route path="/news" element={<News />} />
      <Route path="/about" element={<About />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/what-to-do" element={<WhatToDo />} />
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
      {/* Where the page moves itself once it has read the link, so the token leaves the address bar */}
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/app/security" element={<Gate><Security /></Gate>} />

      {/* Logged-in staff */}
      <Route path="/app/dashboard" element={<Gate><Dashboard /></Gate>} />
      {/* BFP personnel see the fire records only (HistoricalData.jsx) */}
      <Route
        path="/app/history"
        element={
          <Gate roles={["System_Admin", "DRRMO_Officer", "BFP_Personnel"]}>
            <HistoricalData />
          </Gate>
        }
      />
      {/* F7 is one module, Reporting and Analytics, on one page with a tab
          each. DRRMO and Admin only, matching the spec's permission check. */}
      <Route
        path="/app/reports"
        element={
          <Gate roles={["System_Admin", "DRRMO_Officer"]}>
            <ReportingAnalytics />
          </Gate>
        }
      />

      {/* Analytics used to be its own page. Bookmarks, the notification
          links and the module navigation all still point here, so it keeps
          working and lands on that tab. */}
      <Route
        path="/app/analytics"
        element={<Navigate to="/app/reports?tab=analytics" replace />}
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      {/* React Router v7's behaviour now: state updates in a transition, and
          relative links resolved the new way inside "*" routes (none here) */}
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}