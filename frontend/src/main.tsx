import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { AppRoutes } from "./routes/AppRoutes";
import "./shared/styles/global.css";

// Apply stored theme synchronously before React renders,
// so the auth screen (outside AppShell) also respects the saved theme.
const savedTheme = localStorage.getItem("omnicall-theme");
if (savedTheme === "dark" || savedTheme === "light") {
  document.documentElement.setAttribute("data-theme", savedTheme);
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  </React.StrictMode>
);
