import { MedicinesPanel } from "../../components/MedicinesPanel";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Medicines({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="Medicines">
      {() => <MedicinesPanel sampleId={sample.id} />}
    </SamplePage>
  );
}
