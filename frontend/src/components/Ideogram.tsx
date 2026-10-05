// Chromosome ideogram drawn as SVG from UCSC cytoBand data (hg19 / GRCh37).
// No Fancy component exists for this; colours follow the zinc palette.
import type { Band, Marker } from "../api";

const LIGHT: Record<string, string> = {
  gneg: "#f4f4f5", gpos25: "#d4d4d8", gpos50: "#a1a1aa", gpos75: "#71717a", gpos100: "#3f3f46",
  acen: "#fca5a5", gvar: "#c4b5fd", stalk: "#93c5fd",
};
const DARK: Record<string, string> = {
  gneg: "#3f3f46", gpos25: "#52525b", gpos50: "#71717a", gpos75: "#a1a1aa", gpos100: "#d4d4d8",
  acen: "#b91c1c", gvar: "#6d28d9", stalk: "#1d4ed8",
};

type Props = {
  bands: Band[];
  length: number;
  width: number;
  height?: number;
  dark: boolean;
  roh?: { start: number; end: number }[];
  traitMarkers?: Marker[];
  healthMarkers?: Marker[];
  title?: string;
};

export function Ideogram({ bands, length, width, height = 14, dark, roh = [], traitMarkers = [], healthMarkers = [], title }: Props) {
  const colours = dark ? DARK : LIGHT;
  const x = (pos: number) => (pos / length) * width;
  const top = 8; // room above for ROH bars and markers
  const total = top + height + 8;
  return (
    <svg width={width} height={total} role="img" aria-label={title} className="block overflow-visible">
      {title && <title>{title}</title>}
      {roh.map(seg => (
        <rect key={`r${seg.start}`} x={x(seg.start)} y={0} width={Math.max(x(seg.end) - x(seg.start), 1.5)} height={4}
          rx={1} fill={dark ? "#fbbf24" : "#d97706"}>
          <title>Run of homozygosity {(seg.start / 1e6).toFixed(1)}–{(seg.end / 1e6).toFixed(1)} Mb</title>
        </rect>
      ))}
      <g>
        <clipPath id={`clip-${title ?? "c"}-${width}`}>
          <rect x={0} y={top} width={width} height={height} rx={height / 2} />
        </clipPath>
        <g clipPath={`url(#clip-${title ?? "c"}-${width})`}>
          {bands.map(b => (
            <rect key={b.start} x={x(b.start)} y={top} width={Math.max(x(b.end) - x(b.start), 0.5)} height={height}
              fill={colours[b.stain] ?? colours.gneg}>
              <title>{b.band || "band"}</title>
            </rect>
          ))}
        </g>
        <rect x={0.5} y={top + 0.5} width={width - 1} height={height - 1} rx={height / 2} fill="none"
          stroke={dark ? "#71717a" : "#a1a1aa"} />
      </g>
      {traitMarkers.map(m => (
        <line key={`t${m.probe_id}${m.pos}`} x1={x(m.pos)} x2={x(m.pos)} y1={top + height} y2={top + height + 7}
          stroke={dark ? "#8fa2ef" : "#5266bd"} strokeWidth={1.5}>
          <title>{m.probe_id} (trait association)</title>
        </line>
      ))}
      {healthMarkers.map(m => (
        <circle key={`h${m.probe_id}${m.pos}`} cx={x(m.pos)} cy={top + height + 5} r={3}
          fill={dark ? "#f472b6" : "#be185d"}>
          <title>{m.probe_id} (health finding)</title>
        </circle>
      ))}
    </svg>
  );
}
