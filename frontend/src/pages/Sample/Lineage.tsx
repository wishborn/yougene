import { LineagePanel } from "../../components/LineagePanel";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Lineage({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="Lineage">
      {() => <LineagePanel sampleId={sample.id} />}
    </SamplePage>
  );
}
