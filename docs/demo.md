# Five-minute CPU demo

The bundled demonstration uses synthetic NIfTI volumes and a deterministic CPU image-processing
provider. It does not require a GPU or model weights. It is research software only, not a trained
medical model and not for diagnosis, treatment, or clinical decision-making.

1. Run `make demo-data`, `make seed-demo`, and `docker compose up --build`.
2. Open `http://localhost:5173` and select **NeuroAnnotate Demo**.
3. Switch among DWI, ADC, and FLAIR and navigate axial, sagittal, and coronal views.
4. Click **Run AI Segmentation** and wait for the persisted job to move from queued/running to
   completed.
5. Toggle the overlay, adjust opacity, then use Brush/Erase and Undo/Redo.
6. Add an optional note and click **Save Revision**. The saved revision becomes the clean base.
7. Re-open the revision, click **Create Export**, and download the ZIP containing
   `lesion-mask.nii.gz` and `provenance.json`.

For import, retry, dirty-state, revision, and export rules, see [workflow.md](workflow.md).
