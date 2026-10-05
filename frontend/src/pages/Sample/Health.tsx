import { HealthPanel } from "../../components/HealthPanel";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Health({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="Health">
      {() => <HealthPanel sampleId={sample.id} />}
    </SamplePage>
  );
}
