import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createInertiaApp } from "@inertiajs/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { initTheme } from "@particle-academy/react-fancy";
import { registerBuiltinThemes } from "@particle-academy/fancy-echarts";
import { buildFancyAppTree } from "@particle-academy/fancy-inertia";
import "./styles.css";

initTheme();
registerBuiltinThemes();
const queryClient = new QueryClient();
const pages = import.meta.glob("./pages/**/*.tsx", { eager: true });

void createInertiaApp({
  id: "app",
  resolve: name => {
    const page = pages[`./pages/${name}.tsx`];
    if (!page) throw new Error(`Unknown page ${name}`);
    return page as never;
  },
  setup({ el, App, props }) {
    createRoot(el).render(
      <StrictMode>
        {buildFancyAppTree({
          App,
          props,
          // Toast provider and every ECharts module, above the Inertia outlet.
          appRoot: { withECharts: true },
          providers: outlet => <QueryClientProvider client={queryClient}>{outlet}</QueryClientProvider>,
          transition: false,
          // "A new version is available" when the build changes (asset version).
          appUpdate: true,
        })}
      </StrictMode>,
    );
  },
  progress: { color: "#5266bd" },
});
