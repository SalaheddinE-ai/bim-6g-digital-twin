# ADR-005: Geometry pipeline design (M02)

**Status:** accepted (M02)

## Decisions
1. **IfcOpenShell iterator, world coordinates, metres.** Verified on m/cm/mm files: the kernel returns
   metres regardless of the file's length unit, so unit handling is tested, not assumed.
2. **One mesh per BIM element, keyed by GlobalId** (suffixed with the STEP id only if a GlobalId repeats).
   Walls keep opening cut-outs; doors/windows are separate filler meshes.
3. **Spaces are exported as `volume`s**, never as radio obstacles (needed later for room membership and
   receiver grids).
4. **Lossless cleaning only**; no decimation (would change wall thickness; scene is small).
5. **Recentring is optional and invertible** (`auto` only beyond 10 km): `world = mesh + origin_offset`.
6. **Coincident duplicate solids are excluded from the radio scene** (they would double-count attenuation)
   but their data is kept and flagged.
7. **Material classes are assumptions.** The config holds no electromagnetic numbers, only references to
   ITU-R P.2040 types as tabulated in Sionna RT, with documented frequency ranges (tested against the
   installed Sionna table). Priority order (concrete > brick > plasterboard > wood > glass > metal >
   ceiling) is itself an assumption; `overrides` by GlobalId record confirmed facts. ITU `floorboard`
   is deliberately unused: it is only valid from 50 GHz.
8. **Placement cross-check only for walls/doors/windows.** On the real file the check gave 250 false
   alarms for slabs/columns/spaces (shared anchor placements) and 0 for the others; levels vs storey
   elevations are asserted in the acceptance test instead.
9. **Dependency injection** (`tessellator`, `ifc`, `mapper`) so invalid-mesh handling is tested without
   mocking the geometry kernel anywhere else.

## Consequences
M04 consumes `GeometryModel.radio_scene()` + the PLY files + `em_material` labels (and must carry the
"assumed" status into simulation metadata). M07 must model door state explicitly.
