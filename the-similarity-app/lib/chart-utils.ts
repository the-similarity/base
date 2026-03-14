export function formatSigned(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function clampRatio(value: number, min: number, max: number) {
  if (max === min) {
    return 0.5;
  }

  return (value - min) / (max - min);
}

export function pointsToPath(points: Array<{ x: number; y: number }>) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}

export function areaPath(upper: Array<{ x: number; y: number }>, lower: Array<{ x: number; y: number }>) {
  const top = pointsToPath(upper);
  const bottom = [...lower]
    .reverse()
    .map((point) => `L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");

  return `${top} ${bottom} Z`;
}

export function scalePoints(
  values: number[],
  startIndex: number,
  totalSlots: number,
  width: number,
  height: number,
  min: number,
  max: number,
) {
  const denominator = Math.max(totalSlots - 1, 1);

  return values.map((value, index) => {
    const x = ((startIndex + index) / denominator) * width;
    const y = height - clampRatio(value, min, max) * height;
    return { x, y };
  });
}
