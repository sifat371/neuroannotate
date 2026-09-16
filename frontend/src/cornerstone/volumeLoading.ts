type VolumeLoadEvent = {
  framesLoaded?: number;
  framesProcessed?: number;
  totalNumFrames?: number;
};

type LoadableVolume = {
  load: (callback: (...args: unknown[]) => void) => void;
  loadStatus?: {
    loaded?: boolean;
    cancelled?: boolean;
  };
};

/**
 * Cornerstone 5.x volume.load() is callback-based and returns void.
 * Wrapping it in a Promise prevents callers from reading or removing a
 * streaming volume before all frames have actually finished processing.
 */
export function waitForVolumeLoad(volume: LoadableVolume): Promise<void> {
  if (volume.loadStatus?.cancelled) {
    return Promise.reject(new Error('Cornerstone volume loading was cancelled.'));
  }
  if (volume.loadStatus?.loaded) {
    return Promise.resolve();
  }

  return new Promise<void>((resolve, reject) => {
    let settled = false;

    const finish = (...args: unknown[]) => {
      if (settled) return;
      const event = (args[0] ?? {}) as VolumeLoadEvent;
      const total = event.totalNumFrames ?? 0;
      const processed = event.framesProcessed ?? total;

      if (total > 0 && processed < total) return;
      settled = true;

      if (volume.loadStatus?.cancelled) {
        reject(new Error('Cornerstone volume loading was cancelled.'));
        return;
      }

      const loaded = event.framesLoaded ?? total;
      if (total > 0 && loaded < total) {
        reject(new Error(`Cornerstone volume loading failed (${loaded}/${total} frames loaded).`));
        return;
      }

      resolve();
    };

    try {
      volume.load(finish);
    } catch (error) {
      settled = true;
      reject(error);
    }
  });
}
