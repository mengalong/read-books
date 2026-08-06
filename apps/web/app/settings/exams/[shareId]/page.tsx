"use client";

import { useParams } from "next/navigation";

import { ExamShareDetailView } from "@/components/exam-share-detail";

export default function AdminExamManagementDetailPage() {
  const params = useParams<{ shareId: string }>();
  return <ExamShareDetailView admin shareId={params.shareId} />;
}
