import { CallsGrid } from "../../components/CallsGrid";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Calls({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="All calls">
      {() => <CallsGrid sampleId={sample.id} />}
    </SamplePage>
  );
}
