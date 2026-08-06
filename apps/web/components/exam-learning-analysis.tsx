import { CircleCheck, Target } from "lucide-react";

import { formatScore } from "@/lib/format";
import type { ExamWeakKnowledgePoint } from "@/lib/types";

export function ExamLearningAnalysis({
  recommendedDirection,
  weakPoints,
}: {
  recommendedDirection: string | null;
  weakPoints: ExamWeakKnowledgePoint[];
}) {
  if (!recommendedDirection) return null;
  const primaryWeakPoints = weakPoints.slice(0, 3);
  const additionalWeakPoints = weakPoints.slice(3);

  return (
    <section className={`exam-learning-analysis ${weakPoints.length ? "has-weakness" : "is-mastered"}`}>
      <div className="learning-analysis-heading">
        {weakPoints.length ? <Target size={18} /> : <CircleCheck size={18} />}
        <div>
          <h2>{weakPoints.length ? "薄弱知识与深入方向" : "本次掌握情况"}</h2>
          <p>{recommendedDirection}</p>
        </div>
      </div>
      {weakPoints.length > 0 && (
        <div className="weak-knowledge-list">
          {primaryWeakPoints.map((item) => <WeakKnowledgeItem item={item} key={item.knowledge_point} />)}
          {additionalWeakPoints.length > 0 && (
            <details className="additional-weak-points">
              <summary>查看其他 {additionalWeakPoints.length} 个薄弱知识点</summary>
              {additionalWeakPoints.map((item) => <WeakKnowledgeItem item={item} key={item.knowledge_point} />)}
            </details>
          )}
        </div>
      )}
    </section>
  );
}

function WeakKnowledgeItem({ item }: { item: ExamWeakKnowledgePoint }) {
  return (
    <article className="weak-knowledge-item">
      <div className="weak-knowledge-title">
        <strong>{item.knowledge_point}</strong>
        <span>{formatScore(item.score)} / {formatScore(item.max_score)} 分 · {item.score_percentage}%</span>
      </div>
      <p>{item.recommendation}</p>
      {item.focus_points.length > 0 && (
        <div className="weak-focus-points">
          {item.focus_points.map((point) => <span key={point}>{point}</span>)}
        </div>
      )}
    </article>
  );
}
