"use client";

import { useParams } from "next/navigation";

import { ExamShareDetailView } from "@/components/exam-share-detail";

export default function ExamManagementDetailPage() {
  const params = useParams<{ shareId: string }>();
  return <ExamShareDetailView shareId={params.shareId} />;
}
