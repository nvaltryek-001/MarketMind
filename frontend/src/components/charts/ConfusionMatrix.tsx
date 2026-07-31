"use client";

interface ConfusionMatrixProps {
  matrix: number[][]; // 3x3 array
  labels: string[]; // e.g., ["DOWN", "SIDEWAYS", "UP"]
  accuracy: number;
  f1Score: number;
}

export default function ConfusionMatrix({
  matrix,
  labels,
  accuracy,
  f1Score,
}: ConfusionMatrixProps) {
  // We want to color each cell based on proportionally how many of the true class
  // ended up in the predicted class.
  const trueTotals = matrix.map((row) => row.reduce((a, b) => a + b, 0));

  const getCellColor = (rowIndex: number, colIndex: number) => {
    const total = trueTotals[rowIndex];
    if (total === 0) return "bg-slate-800/50";

    const proportion = matrix[rowIndex][colIndex] / total;
    const trueLabel = labels[rowIndex];

    // Determine base color based on the True Label
    // If we're on the diagonal (correct prediction), it's strongly that color.
    // Otherwise, it's weakly that color, or we just map everything neutrally.
    // The prompt specifies:
    // DOWN class color: red, SIDEWAYS: amber, UP: emerald
    // high proportion -> darker fill of the class color

    let r, g, b;
    if (trueLabel.includes("DOWN")) {
      r = 239; g = 68; b = 68; // red-500
    } else if (trueLabel.includes("SIDEWAYS")) {
      r = 245; g = 158; b = 11; // amber-500
    } else {
      r = 16; g = 185; b = 129; // emerald-500
    }

    // Base opacity: up to 0.8 depending on proportion
    const opacity = (proportion * 0.8).toFixed(2);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex-1">
        <div className="grid grid-cols-[auto_1fr] gap-2">
          {/* Empty top-left cell */}
          <div></div>

          {/* Predicted Headers */}
          <div className="flex flex-col text-center">
            <span className="text-xs font-semibold text-slate-400 mb-2">
              Predicted &rarr;
            </span>
            <div className="grid grid-cols-3 gap-1">
              {labels.map((lbl) => (
                <div key={`p-${lbl}`} className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  {lbl}
                </div>
              ))}
            </div>
          </div>

          {/* Actual Header (Rotated) */}
          <div className="flex items-center justify-center">
            <div className="text-xs font-semibold text-slate-400 -rotate-90 whitespace-nowrap">
              &larr; Actual
            </div>
          </div>

          {/* Grid Rows */}
          <div className="grid grid-rows-3 gap-1 grid-cols-1">
            {matrix.map((row, i) => (
              <div key={`row-${i}`} className="grid grid-cols-[auto_1fr] gap-2 items-center">
                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider w-16 text-right">
                  {labels[i]}
                </div>
                <div className="grid grid-cols-3 gap-1">
                  {row.map((val, j) => (
                    <div
                      key={`cell-${i}-${j}`}
                      style={{ backgroundColor: getCellColor(i, j) }}
                      className="h-10 md:h-12 border border-slate-700/50 rounded flex items-center justify-center text-sm font-semibold text-white shadow-inner"
                    >
                      {val}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-6 flex justify-center gap-4">
        <div className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm font-medium text-slate-200">
          Accuracy: {(accuracy * 100).toFixed(1)}%
        </div>
        <div className="px-4 py-2 rounded-lg bg-indigo-500/20 border border-indigo-500/30 text-sm font-medium text-indigo-300">
          F1 Score: {(f1Score * 100).toFixed(1)}%
        </div>
      </div>
    </div>
  );
}
