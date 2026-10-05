import { TraitsPanel } from "../../components/TraitsPanel";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Traits({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="Traits">
      {() => <TraitsPanel sampleId={sample.id} />}
    </SamplePage>
  );
}
