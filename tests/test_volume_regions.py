from __future__ import annotations

import base64
import hashlib
import io
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from autocfd5_aiml.core import volume_regions
from autocfd5_aiml.core.source import index_inline_binary_vtk_xml
from autocfd5_aiml.core.volume_regions import (
    VOLUME_REGION_LABELS,
    VolumeRegionGeometryError,
    build_volume_region_support,
    classify_volume_centres,
)

_ASSIGNMENT_DOMAIN = (
    b"autocfd5-regional-assignment-uint8-v1\0"
    + volume_regions.VOLUME_REGION_DEFINITION.sha256.encode("ascii")
    + b"\0"
)
_COORDINATE_DOMAIN = b"autocfd5-volume-cell-centres-f64le-v1\0"

_HEX_LOCAL = np.asarray(
    [
        [-0.2, -0.2, -0.2],
        [0.2, -0.2, -0.2],
        [0.2, 0.2, -0.2],
        [-0.2, 0.2, -0.2],
        [-0.2, -0.2, 0.2],
        [0.2, -0.2, 0.2],
        [0.2, 0.2, 0.2],
        [-0.2, 0.2, 0.2],
    ],
    dtype=np.float32,
)
_WEDGE_LOCAL = np.asarray(
    [
        [-0.4, -0.3, -0.2],
        [0.4, -0.3, -0.2],
        [0.0, 0.6, -0.2],
        [-0.4, -0.3, 0.2],
        [0.4, -0.3, 0.2],
        [0.0, 0.6, 0.2],
    ],
    dtype=np.float32,
)


@dataclass(frozen=True)
class _SyntheticVTU:
    document: bytes
    points: np.ndarray
    connectivity: np.ndarray
    offsets: np.ndarray
    types: np.ndarray
    faces: np.ndarray | None
    faceoffsets: np.ndarray | None
    raw_payloads: dict[str, bytes]


def _encoded_payload(
    values: np.ndarray,
    *,
    dtype: str,
    byte_order: str,
    separate_header_member: bool,
) -> tuple[str, bytes]:
    prefix = "<" if byte_order == "LittleEndian" else ">"
    normalized = np.asarray(values, dtype=np.dtype(prefix + dtype), order="C")
    payload = normalized.tobytes(order="C")
    header = struct.pack("<Q" if byte_order == "LittleEndian" else ">Q", len(payload))
    if separate_header_member:
        encoded = base64.b64encode(header) + base64.b64encode(payload)
    else:
        encoded = base64.b64encode(header + payload)
    # Exercise XML whitespace removal as well as adversarial decoder chunking.
    wrapped = b"\n".join(encoded[index : index + 5] for index in range(0, len(encoded), 5))
    return wrapped.decode("ascii"), payload


def _synthetic_vtu(
    *,
    byte_order: str = "LittleEndian",
    integer_vtk_type: str = "Int32",
    separate_header_member: bool = False,
    points: np.ndarray | None = None,
    connectivity: np.ndarray | None = None,
    offsets: np.ndarray | None = None,
    types: np.ndarray | None = None,
    faces: np.ndarray | None = None,
    faceoffsets: np.ndarray | None = None,
) -> _SyntheticVTU:
    cell_origins = np.asarray(
        [
            [4.5, 0.0, 1.0],
            [0.0, 0.0, 0.25],
            [-2.0, 0.0, 0.0],
            [0.0, 0.0, 1.25],
        ],
        dtype=np.float32,
    )
    default_points = np.vstack(
        (
            _HEX_LOCAL + cell_origins[0],
            _WEDGE_LOCAL + cell_origins[1],
            _HEX_LOCAL + cell_origins[2],
            _WEDGE_LOCAL + cell_origins[3],
        )
    )
    point_values = np.asarray(default_points if points is None else points)
    connectivity_values = np.asarray(
        np.arange(28, dtype=np.int64) if connectivity is None else connectivity
    )
    offset_values = np.asarray(
        [8, 14, 22, 28] if offsets is None else offsets,
        dtype=np.int64,
    )
    type_values = np.asarray(
        [vtk.VTK_HEXAHEDRON, vtk.VTK_WEDGE, vtk.VTK_HEXAHEDRON, vtk.VTK_WEDGE]
        if types is None
        else types,
        dtype=np.uint8,
    )
    face_values = None if faces is None else np.asarray(faces, dtype=np.int64)
    faceoffset_values = None if faceoffsets is None else np.asarray(faceoffsets, dtype=np.int64)
    if (face_values is None) != (faceoffset_values is None):
        raise ValueError("faces and faceoffsets must appear together")
    integer_code = "i4" if integer_vtk_type == "Int32" else "i8"
    encoded: dict[str, str] = {}
    raw_payloads: dict[str, bytes] = {}
    for name, values, dtype in (
        ("points", point_values, "f4"),
        ("connectivity", connectivity_values, integer_code),
        ("offsets", offset_values, integer_code),
        ("types", type_values, "u1"),
    ):
        encoded[name], raw_payloads[name] = _encoded_payload(
            values,
            dtype=dtype,
            byte_order=byte_order,
            separate_header_member=separate_header_member,
        )
    if face_values is not None and faceoffset_values is not None:
        for name, values in (
            ("faces", face_values),
            ("faceoffsets", faceoffset_values),
        ):
            encoded[name], raw_payloads[name] = _encoded_payload(
                values,
                dtype=integer_code,
                byte_order=byte_order,
                separate_header_member=separate_header_member,
            )
    face_xml = ""
    if face_values is not None:
        face_xml = f'''\n        <DataArray type="{integer_vtk_type}" Name="faces" format="binary">{encoded["faces"]}</DataArray>
        <DataArray type="{integer_vtk_type}" Name="faceoffsets" format="binary">{encoded["faceoffsets"]}</DataArray>'''
    document = f"""<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1" byte_order="{byte_order}" header_type="UInt64">
  <UnstructuredGrid>
    <Piece NumberOfPoints="{point_values.shape[0]}" NumberOfCells="{type_values.size}">
      <Points>
        <DataArray type="Float32" NumberOfComponents="3" format="binary">{encoded["points"]}</DataArray>
      </Points>
      <Cells>
        <DataArray type="{integer_vtk_type}" Name="connectivity" format="binary">{encoded["connectivity"]}</DataArray>
        <DataArray type="{integer_vtk_type}" Name="offsets" format="binary">{encoded["offsets"]}</DataArray>
        <DataArray type="UInt8" Name="types" format="binary">{encoded["types"]}</DataArray>{face_xml}
      </Cells>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
""".encode("ascii")
    return _SyntheticVTU(
        document=document,
        points=np.asarray(point_values, dtype=np.float32),
        connectivity=np.asarray(connectivity_values, dtype=np.int64),
        offsets=np.asarray(offset_values, dtype=np.int64),
        types=type_values,
        faces=face_values,
        faceoffsets=faceoffset_values,
        raw_payloads=raw_payloads,
    )


def _vtk_cell_centres(case: _SyntheticVTU) -> np.ndarray:
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(case.points, deep=True))
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    start = 0
    face_start = 0
    for raw_cell_id, (stop, cell_type) in enumerate(zip(case.offsets, case.types, strict=True)):
        ids = vtk.vtkIdList()
        for point_id in case.connectivity[start : int(stop)]:
            ids.InsertNextId(int(point_id))
        if int(cell_type) == vtk.VTK_POLYHEDRON:
            assert case.faces is not None and case.faceoffsets is not None
            face_stop = int(case.faceoffsets[raw_cell_id])
            stream = case.faces[face_start:face_stop]
            number_of_faces = int(stream[0])
            cursor = 1
            face_cells = vtk.vtkCellArray()
            for _ in range(number_of_faces):
                number_of_points = int(stream[cursor])
                cursor += 1
                point_ids = tuple(
                    int(value) for value in stream[cursor : cursor + number_of_points]
                )
                cursor += number_of_points
                face_cells.InsertNextCell(number_of_points, point_ids)
            assert cursor == stream.size
            grid.InsertNextCell(
                int(cell_type),
                ids.GetNumberOfIds(),
                tuple(int(value) for value in case.connectivity[start : int(stop)]),
                face_cells,
            )
            face_start = face_stop
        else:
            grid.InsertNextCell(int(cell_type), ids)
        start = int(stop)
    centres = vtk.vtkCellCenters()
    centres.SetInputData(grid)
    centres.VertexCellsOff()
    centres.Update()
    return np.asarray(
        vtk_to_numpy(centres.GetOutput().GetPoints().GetData()),
        dtype=np.float64,
    )


def _mixed_synthetic_vtu() -> _SyntheticVTU:
    pyramid_faces = [[0, 3, 2, 1], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
    definitions = [
        (vtk.VTK_TETRA, [(0, 0, 0), (3, 0, 0), (0, 6, 0), (0, 0, 9)], None),
        (
            vtk.VTK_POLYHEDRON,
            [(-1, -1, 5), (1, -1, 5), (1, 1, 5), (-1, 1, 5), (0.2, -0.1, 9)],
            pyramid_faces,
        ),
        (
            vtk.VTK_POLYHEDRON,
            [(3, -1, 5), (5, -1, 5), (5, 1, 5), (3, 1, 5), (4.2, -0.1, 9)],
            pyramid_faces,
        ),
        (
            vtk.VTK_HEXAHEDRON,
            [
                (4, -1, 0),
                (6, -1, 0),
                (6, 1, 0),
                (4, 1, 0),
                (4, -1, 2),
                (6, -1, 2),
                (6, 1, 2),
                (4, 1, 2),
            ],
            None,
        ),
        (
            vtk.VTK_WEDGE,
            [
                (0, 0, 0),
                (3, 0, 0),
                (0, 6, 0),
                (0, 0, 7),
                (3, 0, 8),
                (0, 6, 9),
            ],
            None,
        ),
        (
            vtk.VTK_POLYHEDRON,
            [(-1, 4, 5), (1, 4, 5), (1, 6, 5), (-1, 6, 5), (0.2, 4.9, 9)],
            pyramid_faces,
        ),
        (
            vtk.VTK_PYRAMID,
            [(-1, -1, 0), (2, -1, 0), (3, 2, 0), (-2, 2, 0), (0.2, -0.1, 5)],
            None,
        ),
    ]
    points: list[tuple[float, float, float]] = []
    connectivity: list[int] = []
    offsets: list[int] = []
    types: list[int] = []
    faces: list[int] = []
    faceoffsets: list[int] = []
    for cell_type, cell_points, local_faces in definitions:
        point_start = len(points)
        points.extend(cell_points)
        point_ids = list(range(point_start, point_start + len(cell_points)))
        connectivity.extend(point_ids)
        offsets.append(len(connectivity))
        types.append(cell_type)
        if local_faces is None:
            faceoffsets.append(-1)
        else:
            faces.append(len(local_faces))
            for face in local_faces:
                faces.extend([len(face), *(point_ids[index] for index in face)])
            faceoffsets.append(len(faces))
    return _synthetic_vtu(
        points=np.asarray(points, dtype=np.float32),
        connectivity=np.asarray(connectivity, dtype=np.int64),
        offsets=np.asarray(offsets, dtype=np.int64),
        types=np.asarray(types, dtype=np.uint8),
        faces=np.asarray(faces, dtype=np.int64),
        faceoffsets=np.asarray(faceoffsets, dtype=np.int64),
    )


def _build(case: _SyntheticVTU, *, block_cells: int) -> volume_regions.VolumeRegionSupport:
    stream = io.BytesIO(case.document)
    vtk_index = index_inline_binary_vtk_xml(stream, scan_chunk_size=1)
    return build_volume_region_support(
        stream,
        vtk_index,
        encoded_chunk_size=1,
        calculation_block_cells=block_cells,
    )


def test_volume_coordinate_predicates_use_exact_half_open_boundaries() -> None:
    centres = np.asarray(
        [
            [-0.85, 0.0, np.nextafter(0.75, -np.inf)],
            [-0.85, 0.0, 0.75],
            [3.65, 0.0, 2.499],
            [6.0, 0.0, 0.0],
            [0.0, 1.25, 0.0],
            [0.0, -1.25, 1.0],
            [np.nextafter(3.65, -np.inf), 0.0, 2.0],
            [3.65, 2.0, 0.0],
        ],
        dtype=np.float64,
    )
    assert VOLUME_REGION_LABELS == (
        "underbody_and_wheels",
        "near_body_upper",
        "near_wake",
        "upstream_and_outer",
    )
    assert classify_volume_centres(centres).tolist() == [0, 1, 2, 3, 3, 3, 3, 3]
    with pytest.raises(VolumeRegionGeometryError, match="finite"):
        classify_volume_centres([[np.nan, 0.0, 0.0]])
    with pytest.raises(VolumeRegionGeometryError, match="shape"):
        classify_volume_centres([[0.0, 0.0]])


@pytest.mark.parametrize(
    ("byte_order", "integer_vtk_type", "separate_header_member"),
    [
        ("LittleEndian", "Int32", False),
        ("BigEndian", "Int64", True),
    ],
)
def test_streamed_geometry_matches_vtk_and_retains_exact_hash_evidence(
    byte_order: str,
    integer_vtk_type: str,
    separate_header_member: bool,
) -> None:
    case = _synthetic_vtu(
        byte_order=byte_order,
        integer_vtk_type=integer_vtk_type,
        separate_header_member=separate_header_member,
    )
    expected_centres = _vtk_cell_centres(case)
    expected_codes = classify_volume_centres(expected_centres)
    assert expected_codes.tolist() == [2, 0, 3, 1]

    one_cell_blocks = _build(case, block_cells=1)
    three_cell_blocks = _build(case, block_cells=3)
    assert np.array_equal(one_cell_blocks.codes, expected_codes)
    assert not one_cell_blocks.codes.flags.writeable
    assert np.array_equal(three_cell_blocks.codes, expected_codes)
    assert (
        one_cell_blocks.audit["assignment_identity_sha256"]
        == (three_cell_blocks.audit["assignment_identity_sha256"])
    )
    assert (
        one_cell_blocks.audit["coordinate_identity_sha256"]
        == (three_cell_blocks.audit["coordinate_identity_sha256"])
    )

    raw_codes = expected_codes.tobytes(order="C")
    raw_centres64 = np.asarray(expected_centres, dtype="<f8", order="C").tobytes()
    raw_centres32 = np.asarray(expected_centres, dtype="<f4", order="C").tobytes()
    audit = one_cell_blocks.audit
    assert (
        audit["assignment_identity_sha256"]
        == hashlib.sha256(_ASSIGNMENT_DOMAIN + raw_codes).hexdigest()
    )
    assert (
        audit["coordinate_identity_sha256"]
        == hashlib.sha256(_COORDINATE_DOMAIN + raw_centres64).hexdigest()
    )
    assert audit["coordinate_float64_le_sha256"] == hashlib.sha256(raw_centres64).hexdigest()
    assert audit["coordinate_float32_le_sha256"] == hashlib.sha256(raw_centres32).hexdigest()
    assert audit["region_entity_count"] == {label: 1 for label in VOLUME_REGION_LABELS}
    assert audit["minimum_xyz_m"] == np.min(expected_centres, axis=0).tolist()
    assert audit["maximum_xyz_m"] == np.max(expected_centres, axis=0).tolist()
    assert audit["topology_validation"] == {
        "connectivity_scalar_count": 28,
        "final_offset": 28,
        "offsets_match_fixed_type_arity": True,
        "polyhedron_variable_arity_validated": True,
        "point_ids_in_range": True,
    }
    assert audit["bounded_storage"] == {
        "points": "temporary_raw_file_read_only_memmap",
        "types": "per_block_memmap_copy_then_close",
        "connectivity": "per_block_memmap_copy_then_close",
        "offsets": "per_block_memmap_copy_then_close",
        "faces": "absent",
        "faceoffsets": "absent",
        "region_codes": "returned_uint8_array",
    }
    expected_tuple_counts = {
        "points": case.points.shape[0],
        "connectivity": case.connectivity.size,
        "offsets": case.offsets.size,
        "types": case.types.size,
    }
    expected_scalar_counts = {
        "points": case.points.size,
        "connectivity": case.connectivity.size,
        "offsets": case.offsets.size,
        "types": case.types.size,
    }
    for name, payload in case.raw_payloads.items():
        evidence = audit["geometry_payloads"][name]
        assert evidence["tuple_count"] == expected_tuple_counts[name]
        assert evidence["scalar_count"] == expected_scalar_counts[name]
        assert evidence["decoded_payload_bytes"] == len(payload)
        assert evidence["payload_sha256"] == hashlib.sha256(payload).hexdigest()


def test_wedge_uses_vtk_literal_parametric_centre_not_exact_vertex_mean() -> None:
    case = _synthetic_vtu()
    vtk_centres = _vtk_cell_centres(case)
    wedge_start = int(case.offsets[0])
    wedge_stop = int(case.offsets[1])
    arithmetic_mean = np.mean(
        case.points[case.connectivity[wedge_start:wedge_stop]].astype(np.float64),
        axis=0,
    )
    assert not np.array_equal(vtk_centres[1], arithmetic_mean)
    support = _build(case, block_cells=2)
    expected_raw = np.asarray(vtk_centres, dtype="<f8", order="C").tobytes()
    assert support.audit["coordinate_float64_le_sha256"] == hashlib.sha256(expected_raw).hexdigest()


def test_all_pinned_linear_and_polyhedron_types_match_vtk_9_5_2_exactly() -> None:
    case = _mixed_synthetic_vtu()
    assert case.types.tolist() == [10, 42, 42, 12, 13, 42, 14]
    expected_centres = _vtk_cell_centres(case)
    support_one = _build(case, block_cells=1)
    support_three = _build(case, block_cells=3)
    expected_codes = classify_volume_centres(expected_centres)
    assert np.array_equal(support_one.codes, expected_codes)
    assert np.array_equal(support_three.codes, expected_codes)
    expected64 = np.asarray(expected_centres, dtype="<f8", order="C").tobytes()
    expected32 = np.asarray(expected_centres, dtype="<f4", order="C").tobytes()
    assert (
        support_one.audit["coordinate_float64_le_sha256"] == hashlib.sha256(expected64).hexdigest()
    )
    assert (
        support_one.audit["coordinate_float32_le_sha256"] == hashlib.sha256(expected32).hexdigest()
    )
    assert (
        support_one.audit["coordinate_identity_sha256"]
        == (support_three.audit["coordinate_identity_sha256"])
    )
    assert support_one.audit["vtk_cell_type_counts"] == {
        "10": 1,
        "12": 1,
        "13": 1,
        "14": 1,
        "42": 3,
    }
    assert support_one.audit["topology_validation"]["legacy_faces_faceoffsets_validated"]
    assert support_one.audit["topology_validation"]["polyhedron_face_count"] == 15
    # These deliberately distorted cells expose the non-mean VTK semantics.
    starts = np.r_[0, case.offsets[:-1]]
    for raw_cell_id, cell_type in enumerate(case.types):
        if int(cell_type) not in {
            vtk.VTK_WEDGE,
            vtk.VTK_PYRAMID,
            vtk.VTK_POLYHEDRON,
        }:
            continue
        ids = case.connectivity[starts[raw_cell_id] : case.offsets[raw_cell_id]]
        assert not np.array_equal(
            expected_centres[raw_cell_id],
            np.mean(case.points[ids].astype(np.float64), axis=0),
        )


def test_topology_is_mapped_only_in_owned_blocks_and_all_maps_are_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _mixed_synthetic_vtu()
    real_memmap = np.memmap
    opened: list[tuple[str, tuple[int, ...], int, np.memmap]] = []

    def recording_memmap(
        filename: object,
        dtype: object = np.uint8,
        mode: str = "r+",
        offset: int = 0,
        shape: int | tuple[int, ...] | None = None,
        order: str = "C",
    ) -> np.memmap:
        mapping = real_memmap(
            filename,
            dtype=dtype,
            mode=mode,
            offset=offset,
            shape=shape,
            order=order,
        )
        normalized_shape = tuple(int(value) for value in mapping.shape)
        opened.append((Path(filename).name, normalized_shape, offset, mapping))
        return mapping

    monkeypatch.setattr(volume_regions.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(volume_regions.np, "memmap", recording_memmap)
    support = _build(case, block_cells=2)
    assert support.audit["bounded_storage"]["connectivity"] == ("per_block_memmap_copy_then_close")
    assert list(tmp_path.iterdir()) == []
    assert opened
    assert all(getattr(mapping, "_mmap").closed for *_, mapping in opened)

    by_name: dict[str, list[tuple[int, ...]]] = {}
    for name, shape, _offset, _mapping in opened:
        by_name.setdefault(name, []).append(shape)
    assert by_name["points.raw"] == [(case.points.shape[0], 3)]
    assert max(shape[0] for shape in by_name["types.raw"]) <= 2
    assert max(shape[0] for shape in by_name["offsets.raw"]) <= 2
    assert max(shape[0] for shape in by_name["faceoffsets.raw"]) <= 2
    assert max(shape[0] for shape in by_name["connectivity.raw"]) < (case.connectivity.size)
    assert all(len(shape) == 1 for shape in by_name["faces.raw"])


def test_geometry_block_size_is_hard_capped_independently_of_prediction_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _mixed_synthetic_vtu()
    original = volume_regions._reduce_geometry_blocks
    observed: list[int] = []

    def recording_reducer(**kwargs: object) -> object:
        observed.append(int(kwargs["block_cells"]))
        return original(**kwargs)

    monkeypatch.setattr(volume_regions, "_reduce_geometry_blocks", recording_reducer)
    support = _build(case, block_cells=9_000_000)
    assert observed == [1_000_000]
    assert support.audit["requested_calculation_block_cells"] == 9_000_000
    assert support.audit["calculation_block_cells"] == 1_000_000
    assert support.audit["maximum_geometry_block_cells"] == 1_000_000


@pytest.mark.parametrize(
    ("replacement", "error"),
    [
        ({"types": np.asarray([11, 13, 12, 13], dtype=np.uint8)}, "unsupported"),
        ({"offsets": np.asarray([8, 15, 22, 28])}, "raw_cell_id 1"),
        ({"connectivity": np.append(np.arange(27), 999)}, "invalid point ID"),
        ({"connectivity": np.arange(27)}, "exceeds connectivity"),
        ({"connectivity": np.arange(29)}, "final native cell offset"),
    ],
)
def test_invalid_native_topology_fails_closed_and_removes_temporary_files(
    replacement: dict[str, np.ndarray],
    error: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _synthetic_vtu(**replacement)
    monkeypatch.setattr(volume_regions.tempfile, "tempdir", str(tmp_path))
    with pytest.raises(VolumeRegionGeometryError, match=error):
        _build(case, block_cells=1)
    assert list(tmp_path.iterdir()) == []


def test_nonfinite_unused_point_is_rejected_during_the_point_spool() -> None:
    base = _synthetic_vtu()
    points = np.vstack((base.points, [[np.nan, 0.0, 0.0]])).astype(np.float32)
    case = _synthetic_vtu(points=points)
    with pytest.raises(VolumeRegionGeometryError, match="non-finite"):
        _build(case, block_cells=2)


@pytest.mark.parametrize(
    ("encoded_chunk_size", "calculation_block_cells"),
    [(0, 1), (1, 0), (True, 1), (1, True)],
)
def test_invalid_geometry_chunk_limits_are_rejected(
    encoded_chunk_size: int,
    calculation_block_cells: int,
) -> None:
    case = _synthetic_vtu()
    stream = io.BytesIO(case.document)
    vtk_index = index_inline_binary_vtk_xml(stream)
    with pytest.raises(VolumeRegionGeometryError, match="chunk limits"):
        build_volume_region_support(
            stream,
            vtk_index,
            encoded_chunk_size=encoded_chunk_size,
            calculation_block_cells=calculation_block_cells,
        )
