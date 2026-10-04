import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { initTheme, Toast } from "@particle-academy/react-fancy";
import { registerAll, registerBuiltinThemes } from "@particle-academy/fancy-echarts";
import "./styles.css";
import { App } from "./App";

initTheme();
registerAll();
registerBuiltinThemes();
const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Toast.Provider>
        <App />
      </Toast.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
