import { QcCard } from "../../components/QcCard";
import { SamplePage, type SamplePageProps } from "./SamplePage";

export default function Overview({ sample }: SamplePageProps) {
  return (
    <SamplePage key={sample.id} sample={sample} section="Overview">
      {dark => <QcCard sample={sample} dark={dark} />}
    </SamplePage>
  );
}
