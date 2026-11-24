# Module specifications

## M01 - BIM / IFC ingestion engine

**Contract:** `ingest_ifc(path, storage_dir=None) -> IngestResult(model, ifc_path, json_path,
report_path)`; raises `IfcLoadError` for missing / wrong-extension / empty / non-STEP /
unparseable / unsupported-schema files *before* anything is stored.

| File | Responsibility |
|---|---|
| `modules/bim/schemas.py` | BDM pydantic models (pure) |
| `modules/bim/parser.py` | `load_ifc`, SHA-256, building ID, source description |
| `modules/bim/properties.py` | attributes, psets/qtos, materials, placement, geometry reference |
| `modules/bim/relationships.py` | containment, aggregation, host (void+fill), space boundary, path connection |
| `modules/bim/extractor.py` | `extract_building(ifc, source, building_id) -> BuildingModel` |
| `modules/bim/validator.py` | `validate_building(model) -> ValidationReport` (pure) |
| `modules/bim/report.py` | `export_json`, `load_json`, `build_extraction_report` (pure) |
| `modules/bim/ingest.py` | orchestration + storage |
| `scripts/ingest_ifc.py` | CLI (also writes sample datasets) |

**Element data:** GlobalId, IFC class, name, object type, predefined type, tag, description,
raw scalar attributes, `dimensions_m`, property sets, quantities, materials, spatial context,
placement (m), geometry reference, source IFC schema.

**Relationships:** `aggregates`, `contains`, `hosted_in` (door/window -> wall, via opening),
`bounds_space`, `connects_to`. `hosted_in` carries `host_kind` = `opening` | `aggregate`
(curtain-wall panels).

**Validation codes:** error - `EMPTY_MODEL`, `DUPLICATE_GLOBAL_ID`, `MALFORMED_GLOBAL_ID`,
`MISSING_GLOBAL_ID`; warning - `NO_STOREYS`, `NO_SPATIAL_STRUCTURE`, `MISSING_NAME`,
`NO_SPATIAL_CONTAINER`, `MISSING_GEOMETRY`, `MISSING_MATERIAL`, `MISSING_PLACEMENT`,
`MISSING_DIMENSIONS`, `NO_HOST_ELEMENT`, `DANGLING_RELATIONSHIP`; info - `NO_SPACES`,
`MISSING_PROPERTIES`.

**Run:**
```bash
pytest tests/unit/test_bim_* -v                       # fixture-based
pytest tests/integration/test_bim_real_ifc.py -v      # real IFC in tests/fixtures/real_ifc/
python scripts/ingest_ifc.py tests/fixtures/real_ifc/*.ifc --samples-dir docs/samples
```


## M02 - Geometry processing engine

**Contract:** `build_geometry(model: BuildingModel, ifc_path, *, storage_dir=None, settings=None,
mapper=None, tessellator=None, ifc=None) -> GeometryResult(model: GeometryModel, meshes, geometry_dir,
geometry_path, report_path)`. Input = the M01 Building Data Model + the original IFC. Output = one
cleaned triangle mesh per geometry element (metres, Z up), keyed by BIM GlobalId.

| File | Responsibility |
|---|---|
| `modules/geometry/meshops.py` | pure numpy: transforms, welding, degenerate/unreferenced removal, orientation, watertightness, fingerprint, PLY I/O |
| `modules/geometry/materials.py` | traceable IFC-material -> radio-class mapping (`configs/materials.yaml`) |
| `modules/geometry/tessellate.py` | IfcOpenShell tessellation (world coordinates, metres) |
| `modules/geometry/pipeline.py` | orchestration, validation, recentring, duplicates, persistence |
| `modules/geometry/schemas.py`, `report.py` | `GeometryModel` (pydantic) and markdown report |
| `scripts/build_geometry.py` | CLI: IFC -> M01 ingest -> M02 geometry |

**Coordinate system:** metres, Z up, right-handed, IFC world coordinates (placements applied, no
map conversion). If coordinates exceed `geometry.recenter_threshold_m` (mode `auto`) all meshes are
shifted and `coordinate_system.origin_offset_m` is stored: `world_m = mesh_m + origin_offset_m`.

**Per element:** status (`ok | repaired | invalid | missing | failed`), role (`solid` obstructs radio
waves, `volume` = IfcSpace), bbox, area, volume (closed meshes only), repairs performed, material
assignment (always an assumption), `include_in_radio_scene` + `excluded_reason`, issues.

**Codes:** error - `EMPTY_MESH`, `NON_FINITE_VERTEX`, `FACE_INDEX_OUT_OF_RANGE`, `MALFORMED_MESH`,
`EMPTY_AFTER_CLEANING`, `TESSELLATION_FAILED`; warning - `MISSING_GEOMETRY`, `DUPLICATE_GEOMETRY`,
`INCONSISTENT_ORIENTATION`, `SUSPICIOUS_SIZE`, `PLACEMENT_MISMATCH`, `UNMAPPED_MATERIAL`;
info - `NO_OWN_GEOMETRY` (curtain walls), `NOT_WATERTIGHT`, `NON_MANIFOLD_EDGES`, `COMPOSITE_MATERIAL`.

**Run:**
```bash
python scripts/build_geometry.py tests/fixtures/real_ifc/BuildingBIMModel.ifc
pytest tests/unit/test_geometry_* -v                  # no IfcOpenShell needed
pytest tests/integration/test_geometry_pipeline.py    # synthetic IFC, exact boxes
pytest tests/integration/test_geometry_real_ifc.py    # real building acceptance
```
