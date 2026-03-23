"use client";

interface ParamSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  format?: (value: number) => string;
}

export function ParamSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: ParamSliderProps) {
  const display = format ? format(value) : String(value);

  return (
    <div className="strategy-slider">
      <div className="strategy-slider-header">
        <span className="strategy-slider-label">{label}</span>
        <span className="strategy-slider-value">{display}</span>
      </div>
      <input
        type="range"
        className="strategy-slider-input"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
      <div className="strategy-slider-range">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  );
}
