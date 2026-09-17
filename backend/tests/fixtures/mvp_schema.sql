CREATE TABLE cases (
    id VARCHAR NOT NULL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE modalities (
    id VARCHAR NOT NULL PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    modality VARCHAR(16) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    shape_x INTEGER NOT NULL,
    shape_y INTEGER NOT NULL,
    shape_z INTEGER NOT NULL,
    spacing_x FLOAT NOT NULL,
    spacing_y FLOAT NOT NULL,
    spacing_z FLOAT NOT NULL,
    affine_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE,
    UNIQUE (case_id, modality)
);

CREATE INDEX ix_modalities_case_id ON modalities (case_id);

CREATE TABLE inference_runs (
    id VARCHAR NOT NULL PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    provider VARCHAR(80) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    status VARCHAR(32) NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

CREATE INDEX ix_inference_runs_case_id ON inference_runs (case_id);

CREATE TABLE annotation_revisions (
    id VARCHAR NOT NULL PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    source_inference_id VARCHAR(64) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    note VARCHAR(500),
    created_at DATETIME NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
);

CREATE INDEX ix_annotation_revisions_case_id ON annotation_revisions (case_id);

INSERT INTO cases (id, name, created_at)
VALUES ('case-1', 'Legacy Case', '2026-01-02 03:04:05');

INSERT INTO modalities (
    id, case_id, modality, relative_path,
    shape_x, shape_y, shape_z,
    spacing_x, spacing_y, spacing_z,
    affine_json, created_at
) VALUES
    ('source-adc', 'case-1', 'ADC', 'case-1/modalities/adc.nii.gz',
     10, 11, 12, 1.00005, 1.1, 1.2,
     '[[1.00005,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]',
     '2026-01-02 03:06:00'),
    ('source-dwi', 'case-1', 'DWI', 'case-1/modalities/dwi.nii.gz',
     10, 11, 12, 1.0, 1.1, 1.2, '[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]',
     '2026-01-02 03:05:00'),
    ('source-flair', 'case-1', 'FLAIR', 'case-1/modalities/flair.nii.gz',
     10, 11, 12, 1.0, 1.1, 1.2, '[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]',
     '2026-01-02 03:07:00');

INSERT INTO inference_runs (
    id, case_id, provider, relative_path, status, metadata_json, created_at
) VALUES (
    'inference-1', 'case-1', 'demo', 'case-1/inference/segmentation.nii.gz',
    'completed', '{"algorithm":"legacy-demo"}', '2026-01-02 03:08:00'
);

INSERT INTO annotation_revisions (
    id, case_id, source_inference_id, relative_path, note, created_at
) VALUES (
    'revision-1', 'case-1', 'inference-1', 'case-1/revisions/revision-1.nii.gz',
    'legacy revision', '2026-01-02 03:09:00'
);
