import { forwardRef } from "react";

import { formatDateTime, formatDuration, formatScore, scorePercentage } from "@/lib/format";
import type { ExamAttempt, ExamDeviceType, ExamQuestion } from "@/lib/types";

const deviceTypeLabels: Record<ExamDeviceType, string> = {
  desktop: "电脑",
  mobile: "手机",
  tablet: "平板",
  unknown: "未知终端",
};

const questionTypeLabels: Record<ExamQuestion["question_type"], string> = {
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
};

export const ExamAttemptReport = forwardRef<HTMLDivElement, {
  attempt: ExamAttempt;
  includeSecurity?: boolean;
}>(function ExamAttemptReport({ attempt, includeSecurity = false }, ref) {
  const answerMap = new Map(attempt.answers.map((answer) => [answer.question_id, answer]));
  const percent = scorePercentage(attempt.total_score, attempt.max_score) || 0;
  const weakPoints = attempt.weak_knowledge_points || [];

  return (
    <article aria-hidden="true" className="exam-attempt-report" ref={ref}>
      <header className="exam-report-header">
        <div>
          <span>考试答题与学习报告</span>
          <h1>{attempt.exam_name}</h1>
          <p>{attempt.book_title} · {attempt.quiz_title}</p>
        </div>
        <div className={`exam-report-score ${percent < 60 ? "low" : ""}`}>
          <strong>{formatScore(attempt.total_score)}</strong>
          <span>/ {formatScore(attempt.max_score)} 分</span>
        </div>
      </header>

      <section className="exam-report-meta">
        <ReportMeta label="参与者" value={attempt.participant_name} />
        <ReportMeta label="得分率" value={`${percent}%`} />
        <ReportMeta label="答题用时" value={formatDuration(attempt.elapsed_seconds)} />
        <ReportMeta label="提交时间" value={formatDateTime(attempt.submitted_at)} />
      </section>

      {includeSecurity && (
        <section className="exam-report-security">
          <h2>答题环境记录</h2>
          <div>
            <ReportMeta label="终端类型" value={attempt.device_type ? deviceTypeLabels[attempt.device_type] : "历史记录未采集"} />
            <ReportMeta label="开始 IP" value={attempt.started_ip_address || "未采集"} />
            <ReportMeta label="提交 IP" value={`${attempt.submitted_ip_address || "未采集"}${attempt.ip_changed ? "（提交 IP 已变化）" : ""}`} />
          </div>
          {attempt.user_agent && <p><strong>浏览器信息：</strong>{attempt.user_agent}</p>}
        </section>
      )}

      <section className={`exam-report-learning ${weakPoints.length ? "has-weakness" : ""}`}>
        <div className="exam-report-section-heading">
          <div><span>学习分析</span><h2>{weakPoints.length ? "薄弱知识点与深入学习方向" : "本次掌握情况"}</h2></div>
          <small>{weakPoints.length ? `${weakPoints.length} 个待巩固知识点` : "掌握情况良好"}</small>
        </div>
        <p className="exam-report-direction">{attempt.recommended_direction || "本次答题暂未生成学习建议。"}</p>
        {weakPoints.map((item) => (
          <article className="exam-report-weak-item" key={item.knowledge_point}>
            <div><strong>{item.knowledge_point}</strong><span>{formatScore(item.score)} / {formatScore(item.max_score)} 分 · {item.score_percentage}%</span></div>
            <p>{item.recommendation}</p>
            {item.focus_points.length > 0 && <ul>{item.focus_points.map((point) => <li key={point}>{point}</li>)}</ul>}
          </article>
        ))}
      </section>

      <section className="exam-report-answers">
        <div className="exam-report-section-heading">
          <div><span>答题记录</span><h2>逐题作答明细</h2></div>
          <small>共 {attempt.questions.length} 道题</small>
        </div>
        {attempt.questions.map((question, index) => (
          <ReportQuestion answer={answerMap.get(question.id)} index={index} key={question.id} question={question} />
        ))}
      </section>

      <footer className="exam-report-footer">
        <span>本报告由回卷生成</span>
        <span>开始答题：{formatDateTime(attempt.started_at)}</span>
      </footer>
    </article>
  );
});

function ReportMeta({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function ReportQuestion({
  answer,
  index,
  question,
}: {
  answer: ExamAttempt["answers"][number] | undefined;
  index: number;
  question: ExamQuestion;
}) {
  const selectedText = answer
    ? question.question_type === "short"
      ? answer.text_answer || "未作答"
      : question.options.filter((option) => answer.selected_answers.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；") || "未作答"
    : "未作答";
  const correctText = question.question_type === "short"
    ? question.reference_answer
    : question.options.filter((option) => question.correct_answers?.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；");
  const passed = Boolean(answer && answer.score / answer.max_score >= 0.6);

  return (
    <article className={`exam-report-question ${passed ? "passed" : "missed"}`}>
      <div className="exam-report-question-heading">
        <span>第 {index + 1} 题 · {questionTypeLabels[question.question_type]} · {question.knowledge_point}</span>
        <strong>{answer ? `${formatScore(answer.score)} / ${formatScore(answer.max_score)} 分` : `0 / ${formatScore(question.max_score)} 分`}</strong>
      </div>
      <h3>{question.prompt}</h3>
      <dl>
        <div><dt>参与者答案</dt><dd>{selectedText}</dd></div>
        <div><dt>{question.question_type === "short" ? "参考答案" : "正确答案"}</dt><dd>{correctText || "—"}</dd></div>
      </dl>
      <div className="exam-report-feedback"><strong>评分反馈</strong><p>{answer?.feedback || "本题未作答。"} {question.explanation}</p></div>
      {question.grading_rubric.length > 0 && (
        <div className="exam-report-rubric"><strong>评分要点</strong>{question.grading_rubric.map((rubric) => <span className={answer?.matched_points.includes(rubric.point) ? "matched" : ""} key={rubric.point}>{answer?.matched_points.includes(rubric.point) ? "已覆盖" : "待补充"}：{rubric.point}</span>)}</div>
      )}
    </article>
  );
}
