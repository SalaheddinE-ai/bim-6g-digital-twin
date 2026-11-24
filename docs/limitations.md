# Known limitations

1. **CUDA/OptiX on WSL2**: not available out of the box (`libnvoptix.so.1` missing). Mitsuba
   documents an unofficial workaround that copies files into a Windows system folder and may
   degrade performance. Deferred; everything runs on CPU (LLVM) meanwhile.
2. System Python is 3.14 in the WSL distro; the project uses uv-managed 3.12 (ADR-001).
3. The CPU backend is slower than GPU for large scenes; M00 only runs a tiny box scene.
4. (obsolete) a real IFC has been processed since M01.

## M01 limitations
5. Only walls, curtain walls, doors, windows, slabs, columns, spaces and the spatial hierarchy are extracted.
   Curtain walls, beams, roofs, stairs, furniture, etc. are not (yet).
6. Geometry is referenced, not tessellated (M02). Material layer thicknesses are not extracted.
7. Quantities (`Qto_*`) are kept in raw IFC project units, not converted.
8. Spatial-tree children are limited to extracted classes (no IfcFacility/IfcSpatialZone).
9. The fixture-based IfcOpenShell tests depend on IfcOpenShell 0.9.0.post1 API behaviour.
10. Space-to-element relations come from IfcRelSpaceBoundary only (no geometric containment test;
    that belongs to M03).

## M02 limitations

11. **Material classes are assumptions.** Name rules and category fallbacks only guess a radio class;
    nothing is verified. 154 of 476 radio-scene solids in the sample building carry several matching
    materials and are decided by rule priority, because layer thicknesses are not extracted yet
    (see M01 limitation 6). Confirmed facts go in `overrides` (by GlobalId).
12. Curtain walls (34 in the sample) have no own geometry; their door/window panels carry it. Whether
    glazing/mullion geometry is complete for curtain walls was not examined.
13. Walls keep their opening cut-outs; door/window meshes are separate fillers. M07 (open/close door)
    must handle that explicitly. A closed door = filler mesh present, an open door is NOT modelled yet.
14. Cleaning is lossless only (weld, degenerate and unreferenced removal, orientation fix). There is no
    decimation: not justified at 592 meshes / 2.9 MB, and it would alter wall thickness.
15. 221 of 592 sample meshes are not watertight (non-manifold edges). Reported as `info`; whether
    Sionna RT handles them well is checked in M04, not here.
16. Welding uses grid quantisation (`weld_tolerance_m`), so two vertices straddling a cell border may
    stay separate. Duplicate detection finds coincident identical geometry only, not partial overlaps.
17. The BIM-placement vs mesh cross-check is only meaningful for walls, doors and windows (slabs,
    columns and spaces are anchored elsewhere in Revit exports). Levels are checked against storey
    elevations in the acceptance test instead.
18. PLY files store float32 coordinates (micrometre-level error at building scale).
19. Never verified yet: loading these PLY files into Mitsuba/Sionna (M04), and the sample building was
    processed on a 1-CPU sandbox only; the same tests must be run on the user's machine.
