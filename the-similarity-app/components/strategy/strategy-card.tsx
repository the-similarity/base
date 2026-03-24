"use client";

interface StrategyCardProps {
  icon: string;
  name: string;
  description: string;
  params: string[];
  selected: boolean;
  onClick: () => void;
}

export function StrategyCard({
  icon,
  name,
  description,
  params,
  selected,
  onClick,
}: StrategyCardProps) {
  return (
    <div
      className="strategy-card"
      data-selected={selected}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="strategy-card-icon">{icon}</div>
      <div className="strategy-card-name">{name}</div>
      <div className="strategy-card-desc">{description}</div>
      <div className="strategy-card-params">
        {params.map((p) => (
          <span key={p} className="strategy-card-param">
            {p}
          </span>
        ))}
      </div>
    </div>
  );
}
