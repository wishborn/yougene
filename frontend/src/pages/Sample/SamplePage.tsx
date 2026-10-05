import type { ReactNode } from "react";
import { useTheme } from "@particle-academy/react-fancy";
import type { Sample } from "../../api";
import { AnnotationStatus } from "../../components/AnnotationStatus";
import { AppLayout, PageHeader } from "../../layout/AppLayout";

export type SamplePageProps = { sample: Sample };

/** Shared frame for the per-sample pages (not itself a routed page). */
export function SamplePage({ sample, section, children }: { sample: Sample; section: string;
  children: (dark: boolean) => ReactNode }) {
  const theme = useTheme();
  return (
    <AppLayout title={`${section} · ${sample.display_name}`}>
      <PageHeader eyebrow={section} title={sample.display_name}>
        {[sample.relationship, sample.vendor, sample.build, `${sample.qc.rows.toLocaleString()} probes`]
          .filter(Boolean).join(" · ")}
      </PageHeader>
      <AnnotationStatus sampleId={sample.id} />
      {children(theme.resolved === "dark")}
    </AppLayout>
  );
}
