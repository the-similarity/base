export function SectionHeader({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="section-head">
      <h2 className="section-header">{title}</h2>
      {detail ? <p className="section-detail">{detail}</p> : null}
    </div>
  );
}
