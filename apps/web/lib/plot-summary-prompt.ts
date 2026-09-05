import type { BookSummary } from "@/lib/types";

export function buildPlotSummaryPrompt(book: Pick<BookSummary, "title" | "author" | "resource_type">): string {
  return `你是一名影视资料研究员、剧情结构分析师和事实校验员。

请基于能够实际打开和阅读的官方资料、主流媒体资料、百度百科、中文维基百科和英文 Wikipedia，整理电视剧《${book.title}》的完整分级剧情梗概。资源类型：${book.resource_type === "tv_series" ? "电视剧" : book.resource_type === "movie" ? "电影" : "书籍改编影视资料"}。作者、编剧或主创信息：${book.author || "请从资料中核实"}。

目标是电视剧版本，不是同名电影、小说或其他改编版本。如果存在同名作品，请先区分版本并在 version_notes 中说明。允许剧透，必须覆盖全剧主线、人物行动、事件因果、冲突发展、关系变化、主要转折、结局和主题。

资料规则：
1. 必须打开并阅读来源页面，不要只使用搜索摘要。
2. 重要事实尽量使用两个独立来源交叉核对。
3. 官方或主流媒体资料优先，百度百科和 Wikipedia 作为百科交叉核验；论坛、博客和粉丝内容不能单独作为关键事实依据。
4. 来源冲突必须记录为 conflicted，不能自行隐藏或强行选择。
5. 无法确认的集数、场景顺序、人物关系或结局细节必须使用 null、空数组或 confidence=unknown，不得凭记忆补全。
6. 不要大段复制网页或字幕，不要整理经典台词；剧情资料应使用自己的话概括。

请按全剧、季、集、事件四级整理。events 是最重要的数组，每个事件必须是一个独立、可判断的事实，并分别填写 cause、action、result、future_impact。每个事件还必须记录 characters、relationship_changes、conflict_tags、theme_tags、importance、source_refs、confidence、question_usable 和 source_kind。source_kind 只能是 plot_source、dialogue_source 或 both_source；剧情事件不要只依赖台词。

只输出合法 JSON，不输出 Markdown 或其他说明。顶层结构必须包含：
{
  "schema_version": "plot_summary.v1",
  "work": {"title": "${book.title}", "resource_type": "tv_series", "version_label": "", "release_year": null, "director": [], "screenwriter": [], "version_notes": "", "source_refs": [], "confidence": "confirmed"},
  "source_registry": [],
  "series_overview": {"one_sentence_summary": "", "detailed_summary": "", "historical_or_story_background": "", "core_conflicts": [], "major_themes": [], "ending_summary": "", "key_turning_points": [], "source_refs": [], "confidence": "confirmed|probable|conflicted|unknown"},
  "seasons": [{"season_number": 1, "summary": "", "episodes": []}],
  "events": [{"event_id": "s01e01-event-001", "level": "event", "season_number": 1, "episode_number": 1, "sequence": 1, "title": "", "summary": "", "cause": "", "action": "", "result": "", "future_impact": "", "characters": [], "relationship_changes": [], "conflict_tags": [], "theme_tags": [], "importance": "high|medium|low", "source_kind": "plot_source|dialogue_source|both_source", "source_refs": [], "confidence": "confirmed|probable|conflicted|unknown", "question_usable": true}],
  "character_profiles": [],
  "relationship_arcs": [],
  "major_story_arcs": [],
  "global_facts": [],
  "uncertainties": []
}

输出前检查所有 source_refs 是否存在于 source_registry，event_id 是否唯一，是否区分演员和角色，是否保留来源冲突，并确保 JSON 可被标准解析器直接解析。如果内容过长，按每 5 集分批输出，但必须保持 schema_version、source_id 和 event_id 稳定。`;
}
