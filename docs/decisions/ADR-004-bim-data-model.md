# ADR-004: Building Data Model (BDM) and IFC ingestion design (M01)

**Status:** accepted (M01)

## Decisions
1. **Pure-pydantic BDM** (`modules/bim/schemas.py`, `extra="forbid"`), JSON-serialisable. Only
   `parser/properties/relationships/extractor/ingest` import IfcOpenShell (lazily), so the model,
   validator and report run and are tested without it.
2. **Elements are a flat list + explicit relationship list + a spatial tree.** A list (not a
   dict keyed by GlobalId) so that duplicate GlobalIds stay visible to the validator.
3. **GlobalId is the only stable key.** STEP ids (`ifc_step_id`) are stored for debugging only.
4. **Metres everywhere** in the BDM (placement, `dimensions_m`). Raw attributes and quantities keep
   the IFC project unit; the factor is stored in `length_unit_scale_m`.
5. **Absolute placement** (PlacementRelTo chain resolved) as 4x4 matrix + origin + Z heading.
6. **Geometry is referenced, not tessellated** (`GeometryRef`, falls back to the type's
   RepresentationMaps). Tessellation is M02.
7. **Missing data stays missing.** Nothing is defaulted or inferred; the validator reports it
   (`MISSING_*` warnings), and per-category completeness is published.
8. **Validation levels:** error = unusable identity (empty model, duplicate/malformed/missing
   GlobalId); warning = incomplete for downstream use; info = cosmetic.
9. **Building ID = SHA-256 prefix of the file** (`bld_<12 hex>`): same content -> same ID, and
   the stored original (`storage/ifc/<id>/original.ifc`, read-only) is never overwritten.
10. **Extracted classes:** project, site, building, storey, space, wall, curtain_wall, door,
    window, slab, column (subtypes included). Other classes are out of scope until needed.

## Consequences
Scenario edits (M07) must create new derived data, never mutate the stored original/BDM.

## Amendment (r2): curtain-wall panels
Real Revit export (`BuildingBIMModel.ifc`) had 17 IfcDoor/IfcWindow panels with no Voids/Fills
host and 30 dangling `aggregates` relations: the panels are aggregated into an `IfcCurtainWall`.
`IfcCurtainWall` is now extracted, and a door/window aggregated by a building element gets a
`hosted_in` relation with `host_kind="aggregate"` (`"opening"` for Voids+Fills hosts). Downstream
modules must not treat aggregate-hosted panels as operable doors without checking type/operation.
