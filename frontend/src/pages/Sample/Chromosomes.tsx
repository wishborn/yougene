import { ExplorerPanel } from "../../components/ExplorerPanel";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Chromosomes({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="Chromosomes">
      {dark => <ExplorerPanel sampleId={sample.id} dark={dark} />}
    </SamplePage>
  );
}
