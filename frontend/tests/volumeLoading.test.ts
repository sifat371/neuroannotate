import { describe, expect, test, vi } from 'vitest';
import { waitForVolumeLoad } from '../src/cornerstone/volumeLoading';

describe('waitForVolumeLoad', () => {
  test('waits for the Cornerstone completion callback', async () => {
    let callback: ((...args: unknown[]) => void) | undefined;
    const volume = {
      loadStatus: { loaded: false, cancelled: false },
      load: vi.fn((cb: (...args: unknown[]) => void) => {
        callback = cb;
      }),
    };

    let resolved = false;
    const promise = waitForVolumeLoad(volume).then(() => {
      resolved = true;
    });

    await Promise.resolve();
    expect(resolved).toBe(false);
    expect(volume.load).toHaveBeenCalledTimes(1);

    callback?.({ framesLoaded: 48, framesProcessed: 48, totalNumFrames: 48 });
    await promise;
    expect(resolved).toBe(true);
  });

  test('rejects when Cornerstone finishes with missing frames', async () => {
    let callback: ((...args: unknown[]) => void) | undefined;
    const volume = {
      loadStatus: { loaded: false, cancelled: false },
      load: (cb: (...args: unknown[]) => void) => {
        callback = cb;
      },
    };

    const promise = waitForVolumeLoad(volume);
    callback?.({ framesLoaded: 47, framesProcessed: 48, totalNumFrames: 48 });

    await expect(promise).rejects.toThrow('47/48');
  });
});
