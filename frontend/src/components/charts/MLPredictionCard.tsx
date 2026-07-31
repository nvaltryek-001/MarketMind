"use client";

import type { MLPrediction } from "@/lib/api";
import FeatureImportanceChart from "./FeatureImportanceChart";
import ConfusionMatrix from "./ConfusionMatrix";

interface MLPredictionCardProps {
  prediction: MLPrediction;
}

export default function MLPredictionCard({ prediction }: MLPredictionCardProps) {
  // Determine direction indicator styles
  let dirIcon = "→";
  let dirColor = "text-amber-500";
  let dirText = "NEUTRAL SIGNAL";

  if (prediction.predicted_direction === "UP") {
    dirIcon = "↑";
    dirColor = "text-emerald-500";
    dirText = "BULLISH SIGNAL";
  } else if (prediction.predicted_direction === "DOWN") {
    dirIcon = "↓";
    dirColor = "text-red-500";
    dirText = "BEARISH SIGNAL";
  }

  return (
    <div className="w-full bg-slate-800/50 border border-slate-700 rounded-2xl p-6 shadow-lg shadow-slate-900/20 backdrop-blur-sm">
      {/* Top Section */}
      <div className="flex items-center justify-between mb-8 border-b border-slate-700/50 pb-4">
        <div className="bg-slate-700/50 border border-slate-600 px-3 py-1 rounded-full text-xs font-semibold text-slate-300">
          {prediction.model_name || "XGBoost Classifier"}
        </div>
        <div className="text-sm font-medium text-slate-400 uppercase tracking-wider">
          {prediction.prediction_horizon || "5-day Direction Forecast"}
        </div>
      </div>

      {/* Center - Signal Overview */}
      <div className="flex flex-col items-center justify-center mb-10">
        <div className="flex items-center gap-4 mb-2">
          <span className={`text-6xl font-light ${dirColor}`}>{dirIcon}</span>
          <span className={`text-3xl font-extrabold tracking-tight ${dirColor}`}>
            {dirText}
          </span>
        </div>
        <div className="text-xl font-medium text-slate-300 mb-6">
          {(prediction.prediction_confidence * 100).toFixed(1)}% confidence
        </div>

        <div className="text-sm text-slate-500 flex items-center gap-2">
          <span>Trained on {prediction.model_metrics.training_samples.toLocaleString()} samples</span>
          <span className="text-slate-600">•</span>
          <span>{prediction.feature_count} features</span>
        </div>
      </div>

      {/* Bottom Row - Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-4">
        {/* Left Col - Feature Importance */}
        <div className="bg-slate-900/40 p-5 rounded-xl border border-slate-700/50">
          <h3 className="text-sm font-semibold text-slate-300 mb-4 px-1">Top Predictive Features</h3>
          <FeatureImportanceChart importances={prediction.feature_importances} />
        </div>

        {/* Right Col - Model Performance */}
        <div className="bg-slate-900/40 p-5 rounded-xl border border-slate-700/50 flex flex-col">
          <h3 className="text-sm font-semibold text-slate-300 mb-4 px-1">Model Performance & Confusion Matrix</h3>
          <div className="flex-1 flex items-center justify-center">
            <ConfusionMatrix
              matrix={prediction.model_metrics.confusion_matrix}
              labels={prediction.model_metrics.class_labels}
              accuracy={prediction.model_metrics.accuracy}
              f1Score={prediction.model_metrics.f1_score}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
