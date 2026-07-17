export type StudyAssetKind = "pdf" | "image" | "video" | "audio";

export interface StudyAsset {
  id: string;
  name: string;
  kind: StudyAssetKind;
  status: "review_required";
}
