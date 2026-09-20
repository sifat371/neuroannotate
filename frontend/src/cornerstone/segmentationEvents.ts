export type SegmentationDataModifiedDetail = {
  segmentationId?: string;
  modifiedSlicesToUse?: number[];
  segmentIndex?: number;
};

export function isUserSegmentationEditEvent(
  detail: SegmentationDataModifiedDetail | undefined,
  segmentationId: string,
): boolean {
  return detail?.segmentationId === segmentationId
    && Array.isArray(detail.modifiedSlicesToUse)
    && detail.modifiedSlicesToUse.length > 0;
}
